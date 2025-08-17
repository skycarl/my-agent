import json
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel
from app.core.auth import verify_token
from app.models.tasks import (
    TelegramMessageRequest,
    TelegramMessageResponse,
    AlertRequest,
    AlertResponse,
    AgentProcessingMetadata,
)

from app.core.settings import config
from app.core.timezone_utils import now_local

# Import the agents and Runner
from agents import Runner
from app.agents.orchestrator_agent import create_orchestrator_agent

router = APIRouter()


class Message(BaseModel):
    """Individual message in a conversation."""

    role: str  # "user", "assistant", "system"
    content: str


class AgentRequest(BaseModel):
    """Request model for the agent_response endpoint."""

    input: Optional[str] = None  # Single user input (for simple requests)
    messages: Optional[List[Message]] = (
        None  # Conversation history (for continued conversations)
    )
    model: Optional[str] = None  # Optional model override

    def model_post_init(self, __context) -> None:
        """Validate that either input or messages is provided, but not both."""
        if self.input is not None and self.messages is not None:
            raise ValueError(
                "Provide either 'input' for simple requests or 'messages' for conversation history, not both"
            )
        if self.input is None and self.messages is None:
            raise ValueError("Must provide either 'input' or 'messages'")
        if self.messages is not None and len(self.messages) == 0:
            raise ValueError("If providing 'messages', the list cannot be empty")


class AgentResponse(BaseModel):
    """Response model for the agent_response endpoint."""

    response: str  # The final agent response
    agent_name: str  # Name of the agent that handled the request
    success: bool  # Whether the request was successful


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str


class ModelsResponse(BaseModel):
    """Models endpoint response model."""

    models: list[str]
    default_model: str = config.default_model


@router.get("/healthcheck", status_code=200, response_model=HealthResponse)
def healthcheck():
    """Health check endpoint."""
    logger.debug("Health check endpoint called")
    return HealthResponse(status="healthy")


@router.get("/models", status_code=200, response_model=ModelsResponse)
def get_models():
    """Get list of available OpenAI models."""
    logger.debug("Models endpoint called")
    return ModelsResponse(
        models=config.valid_openai_models, default_model=config.default_model
    )


@router.post("/agent_response", status_code=200, dependencies=[Depends(verify_token)])
async def create_agent_response(request: AgentRequest):
    """
    Process user message through agents and send response directly via Telegram.

    This endpoint uses async processing - it adds the user message to conversation
    history, processes it through agents, and sends the response directly to the
    user via Telegram instead of returning it to the calling bot.

    Args:
        request: The request containing the user input

    Returns:
        Simple success confirmation
    """
    try:
        from app.core.conversation_manager import get_conversation_manager
        from app.core.agent_response_handler import AgentResponseHandler

        conversation_manager = get_conversation_manager()

        # Extract user message from request
        if request.input is not None:
            user_message = request.input
            logger.debug(f"Received single input request: {request.input}")
        elif request.messages is not None and len(request.messages) > 0:
            # Take the last message as the new user input
            user_message = request.messages[-1].content
            logger.debug(
                f"Received conversation with {len(request.messages)} messages, processing last message"
            )
        else:
            raise HTTPException(status_code=400, detail="No input or messages provided")

        # Add user message to persistent conversation history
        conversation_manager.add_message(
            role="user", content=user_message, message_type="chat"
        )

        # Get conversation history from disk for agent processing
        conversation_history = conversation_manager.get_conversation_history(
            max_messages=config.max_conversation_history
        )

        # Determine which model to use (default to config default for agents)
        model = request.model or config.default_model
        logger.debug(f"Using model '{model}' for this agent request")

        # Validate the model
        if model not in config.valid_openai_models:
            logger.warning(f"Invalid model requested: {model}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model '{model}'. Available models: {', '.join(config.valid_openai_models)}",
            )

        # Create orchestrator agent with the requested model
        logger.debug(f"Creating orchestrator agent with model '{model}'")
        orchestrator_agent = create_orchestrator_agent(model)

        # Ensure OpenAI API key is available
        if not config.openai_api_key:
            raise HTTPException(
                status_code=500,
                detail="OpenAI API key is not configured. Please set the OPENAI_API_KEY environment variable.",
            )

        # Set the OpenAI configuration in environment for the Agents SDK
        import os

        os.environ["OPENAI_API_KEY"] = config.openai_api_key
        os.environ["OPENAI_TIMEOUT"] = str(config.openai_timeout)
        os.environ["OPENAI_MAX_RETRIES"] = str(config.openai_max_retries)

        # Run the agent workflow using the Orchestrator
        logger.debug("Running agent workflow with Orchestrator")
        result = await Runner.run(orchestrator_agent, input=conversation_history)

        logger.debug("Agent workflow completed successfully")
        logger.debug(f"Response: {result.final_output}")

        # Process agent response through unified handler
        (
            should_respond,
            response_message,
        ) = await AgentResponseHandler.process_user_query_response(
            response=result.final_output, user_id=config.authorized_user_id
        )

        if should_respond and response_message.strip():
            # Add agent response to conversation history
            conversation_manager.add_message(
                role="assistant", content=response_message, message_type="chat"
            )

            # Send response directly to user via Telegram
            try:
                from app.core.telegram_client import telegram_client

                target_user_id = config.authorized_user_id
                if target_user_id:
                    success, message_id = await telegram_client.send_message(
                        user_id=target_user_id,
                        message=response_message,
                        parse_mode="HTML",
                    )

                    if success:
                        logger.info(
                            "Successfully sent agent response to user via Telegram"
                        )
                    else:
                        logger.warning(
                            "Failed to send agent response to user via Telegram"
                        )
                else:
                    logger.warning(
                        "No authorized user ID configured for sending response"
                    )

            except Exception as e:
                logger.error(f"Error sending agent response via Telegram: {e}")
                # Don't fail the request if Telegram sending fails
        else:
            logger.info("Agent determined no response should be sent to user")

        # Return simple success confirmation
        return JSONResponse(
            content={
                "success": True,
                "message": "Message processed successfully",
                "response_sent": should_respond,
            }
        )

    except Exception as e:
        logger.error(f"Error in /agent_response endpoint: {str(e)}")

        # Send error message directly to user via Telegram
        try:
            from app.core.telegram_client import telegram_client

            target_user_id = config.authorized_user_id
            if target_user_id:
                error_message = (
                    f"Sorry, I encountered an error processing your request: {str(e)}"
                )
                await telegram_client.send_message(
                    user_id=target_user_id,
                    message=error_message,
                    parse_mode="HTML",
                )
                logger.info("Sent error message to user via Telegram")

        except Exception as telegram_error:
            logger.error(f"Failed to send error message via Telegram: {telegram_error}")

        # Return error response
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Failed to process message: {str(e)}",
            },
        )


@router.post("/process_alert", status_code=201, dependencies=[Depends(verify_token)])
async def process_alert(request: AlertRequest):
    """
    Process an alert through the agent system and store the result.

    This endpoint receives alerts from the email sink service or other sources,
    processes them through the orchestrator agent system, and stores the results
    with agent processing metadata.

    Args:
        request: The alert data to process

    Returns:
        Success confirmation with alert ID and agent processing metadata
    """
    start_time = now_local()
    agent_metadata = AgentProcessingMetadata(
        success=False,
        primary_agent=None,
        actions_taken=[],
        agent_response=None,
        processing_time_ms=None,
        error_message=None,
    )

    try:
        # Format alert as instructions for the orchestrator agent
        alert_data = {
            "uid": request.uid,
            "subject": request.subject,
            "body": request.body,
            "sender": request.sender,
            "date": request.date.isoformat(),
            "alert_type": request.alert_type,
        }

        agent_input = f"Process this alert: {json.dumps(alert_data)}"

        logger.debug(f"Processing alert {request.uid} through orchestrator agent")
        logger.debug(f"Alert data: {alert_data}")

        # Ensure OpenAI API key is available
        if not config.openai_api_key:
            raise HTTPException(
                status_code=500,
                detail="OpenAI API key is not configured. Please set the OPENAI_API_KEY environment variable.",
            )

        # Set the OpenAI configuration in environment for the Agents SDK
        import os

        os.environ["OPENAI_API_KEY"] = config.openai_api_key
        os.environ["OPENAI_TIMEOUT"] = str(config.openai_timeout)
        os.environ["OPENAI_MAX_RETRIES"] = str(config.openai_max_retries)

        # Create orchestrator agent with default model for alert processing
        logger.debug("Creating orchestrator agent for alert processing")
        orchestrator_agent = create_orchestrator_agent()

        # Process alert through orchestrator agent
        try:
            result = await Runner.run(orchestrator_agent, input=agent_input)

            # Extract agent processing metadata
            processing_time = (now_local() - start_time).total_seconds() * 1000
            agent_metadata.success = True
            agent_metadata.agent_response = result.final_output
            agent_metadata.processing_time_ms = int(processing_time)
            agent_metadata.primary_agent = (
                "Orchestrator"  # Could be updated if we can detect handoffs
            )

            # Process agent response through unified handler
            from app.core.agent_response_handler import AgentResponseHandler

            alert_processing_result = await AgentResponseHandler.process_alert_response(
                response=result.final_output, alert_id=request.uid
            )

            # Update agent metadata based on processing result
            if alert_processing_result["notification_sent"]:
                agent_metadata.actions_taken = ["alert_processed", "notification_sent"]
                logger.info(
                    f"Successfully processed alert {request.uid} and sent notification"
                )
            else:
                # Check if notification was intentionally skipped or if there was an error
                metadata = alert_processing_result["metadata"]
                notification_decision = metadata.get("notification_decision")

                if (
                    notification_decision
                    and notification_decision.get("notify_user") is False
                ):
                    agent_metadata.actions_taken = [
                        "alert_processed",
                        "notification_not_needed",
                    ]
                    rationale = notification_decision.get("rationale", "")
                    logger.info(
                        f"Agent determined no notification needed for alert {request.uid}: {rationale}"
                    )
                elif metadata.get("error"):
                    agent_metadata.actions_taken = [
                        "alert_processed",
                        "notification_error",
                    ]
                    logger.error(
                        f"Error processing alert {request.uid}: {metadata['error']}"
                    )
                elif not metadata.get("has_json"):
                    # Agent response had no JSON structure - likely a regular response
                    agent_metadata.actions_taken = [
                        "alert_processed",
                        "no_json_structure",
                    ]
                    logger.info(
                        f"Alert {request.uid} processed with regular response (no JSON structure)"
                    )
                else:
                    agent_metadata.actions_taken = [
                        "alert_processed",
                        "notification_skipped",
                    ]
                    logger.info(
                        f"Alert {request.uid} processed but no notification sent"
                    )

            logger.info(f"Successfully processed alert {request.uid} through agents")
            logger.debug(f"Agent response: {result.final_output}")

        except Exception as e:
            processing_time = (now_local() - start_time).total_seconds() * 1000
            agent_metadata.success = False
            agent_metadata.error_message = f"Agent processing failed: {str(e)}"
            agent_metadata.processing_time_ms = int(processing_time)

            logger.error(f"Agent processing failed for alert {request.uid}: {e}")
            # Continue to store the alert even if agent processing failed

        # Store alert with agent metadata
        storage_dir = Path(config.storage_path)
        storage_dir.mkdir(exist_ok=True)

        # Define the alerts file path (keeping same file name for compatibility)
        alerts_file = storage_dir / "commute_alerts.json"

        # Load existing alerts or create empty list
        alerts = []
        if alerts_file.exists():
            try:
                with open(alerts_file, "r", encoding="utf-8") as f:
                    alerts = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logger.warning(f"Error reading existing alerts file: {e}")
                alerts = []

        # Create the alert record with agent metadata
        alert_record = {
            "id": f"alert_{len(alerts) + 1}_{request.uid}",
            "uid": request.uid,
            "subject": request.subject,
            "body": request.body,
            "sender": request.sender,
            "received_date": request.date.isoformat(),
            "stored_date": now_local().isoformat(),
            "alert_type": request.alert_type,
            "agent_processing": agent_metadata.model_dump(),
        }

        # Add to alerts list
        alerts.append(alert_record)

        # Write back to file with proper error handling
        try:
            with open(alerts_file, "w", encoding="utf-8") as f:
                json.dump(alerts, f, indent=2, ensure_ascii=False, default=str)
        except Exception as e:
            logger.error(f"Failed to write alerts to file: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to store alert to persistent storage"
            )

        logger.info(
            f"Successfully stored alert {alert_record['id']} from {request.sender} "
            f"with agent processing {'success' if agent_metadata.success else 'failure'}"
        )

        # Return success response
        response = AlertResponse(
            success=True,
            message="Alert processed and stored successfully",
            alert_id=alert_record["id"],
            agent_processing=agent_metadata,
        )

        return JSONResponse(content=jsonable_encoder(response))

    except Exception as e:
        processing_time = (now_local() - start_time).total_seconds() * 1000
        logger.error(f"Error in /process_alert endpoint: {str(e)}")

        # Update agent metadata with error info
        agent_metadata.success = False
        agent_metadata.error_message = f"Endpoint error: {str(e)}"
        agent_metadata.processing_time_ms = int(processing_time)

        # Return error response
        error_response = AlertResponse(
            success=False,
            message=f"Failed to process alert: {str(e)}",
            alert_id="",
            agent_processing=agent_metadata,
        )
        return JSONResponse(status_code=500, content=jsonable_encoder(error_response))


@router.post(
    "/clear_conversation", status_code=200, dependencies=[Depends(verify_token)]
)
async def clear_conversation():
    """
    Clear conversation history for the authorized user.

    This endpoint is called by the Telegram bot when the user uses the /clear command.

    Returns:
        Success confirmation
    """
    try:
        from app.core.conversation_manager import get_conversation_manager

        conversation_manager = get_conversation_manager()
        success = conversation_manager.clear_conversation_history()

        if success:
            logger.info("Successfully cleared conversation history")
            return JSONResponse(
                content={
                    "success": True,
                    "message": "Conversation history cleared successfully",
                }
            )
        else:
            logger.warning("Failed to clear conversation history")
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": "Failed to clear conversation history",
                },
            )

    except Exception as e:
        logger.error(f"Error in /clear_conversation endpoint: {str(e)}")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": f"Failed to clear conversation history: {str(e)}",
            },
        )


@router.post(
    "/send_telegram_message", status_code=200, dependencies=[Depends(verify_token)]
)
async def send_telegram_message(request: TelegramMessageRequest):
    """
    Send a message to a Telegram user.

    This endpoint allows scheduled tasks and other services to send messages
    to Telegram users. If no user_id is specified, it sends to the authorized user.

    Args:
        request: The message request with user_id and message text

    Returns:
        Success confirmation with message details
    """
    try:
        # Import here to avoid circular imports
        from app.core.telegram_client import telegram_client

        # Determine target user ID
        target_user_id = request.user_id or config.authorized_user_id

        if not target_user_id:
            raise HTTPException(
                status_code=400,
                detail="No target user specified and no authorized user configured",
            )

        logger.debug(
            f"Sending Telegram message to user {target_user_id}: {request.message}"
        )

        # Send the message
        success, message_id = await telegram_client.send_message(
            user_id=target_user_id,
            message=request.message,
            parse_mode=request.parse_mode,
        )

        if success:
            logger.info(f"Successfully sent Telegram message to user {target_user_id}")
            response = TelegramMessageResponse(
                success=True,
                message="Message sent successfully",
                telegram_message_id=message_id,
            )
            return JSONResponse(content=jsonable_encoder(response))
        else:
            logger.warning(f"Failed to send Telegram message to user {target_user_id}")
            response = TelegramMessageResponse(
                success=False, message="Failed to send message"
            )
            return JSONResponse(status_code=500, content=jsonable_encoder(response))

    except Exception as e:
        logger.error(f"Error in /send_telegram_message endpoint: {str(e)}")

        # Return error response
        error_response = TelegramMessageResponse(
            success=False, message=f"Failed to send message: {str(e)}"
        )
        return JSONResponse(status_code=500, content=jsonable_encoder(error_response))
