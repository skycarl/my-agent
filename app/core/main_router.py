import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel
from app.core.auth import verify_token
from app.models.tasks import TelegramMessageRequest, TelegramMessageResponse

from app.core.settings import config

# Import the agents and Runner
from agents import Runner
from app.agents import orchestrator_agent

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
    default_model: str = "gpt-4o"


class CommuteAlertRequest(BaseModel):
    """Request model for commute alert data."""

    uid: str
    subject: str
    body: str
    sender: str
    date: datetime
    alert_type: str = "email"


class CommuteAlertResponse(BaseModel):
    """Response model for commute alert storage."""

    success: bool
    message: str
    alert_id: str


@router.get("/healthcheck", status_code=200, response_model=HealthResponse)
def healthcheck():
    """Health check endpoint."""
    logger.debug("Health check endpoint called")
    return HealthResponse(status="healthy")


@router.get("/models", status_code=200, response_model=ModelsResponse)
def get_models():
    """Get list of available OpenAI models."""
    logger.debug("Models endpoint called")
    return ModelsResponse(models=config.valid_openai_models, default_model="gpt-4o")


@router.post("/agent_response", status_code=200, dependencies=[Depends(verify_token)])
async def create_agent_response(request: AgentRequest):
    """
    Create a response using OpenAI Agents SDK with agent handoffs.

    This endpoint uses an Orchestrator agent that can delegate tasks to
    specialized agents like the Gardener agent for garden-related queries.

    Args:
        request: The request containing the user input

    Returns:
        The agent response with metadata
    """
    try:
        # Prepare input for agents SDK
        if request.input is not None:
            agent_input = request.input
            logger.debug(f"Received single input request: {request.input}")
        elif request.messages is not None:
            # Convert messages to format expected by agents SDK
            agent_input = [
                {"role": msg.role, "content": msg.content} for msg in request.messages
            ]
            logger.debug(
                f"Received conversation history with {len(request.messages)} messages"
            )
        else:
            # This should not happen due to our validation, but type checker needs it
            raise HTTPException(status_code=400, detail="No input or messages provided")

        # Determine which model to use (default to gpt-4o-mini for agents)
        model = request.model or "gpt-4o-mini"
        logger.debug(f"Using model '{model}' for this agent request")

        # Validate the model
        if model not in config.valid_openai_models:
            logger.warning(f"Invalid model requested: {model}")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid model '{model}'. Available models: {', '.join(config.valid_openai_models)}",
            )

        # Update the orchestrator agent model if different from default
        if model != orchestrator_agent.model:
            logger.debug(f"Updating orchestrator agent model to {model}")
            orchestrator_agent.model = model

        # Ensure OpenAI API key is available
        if not config.openai_api_key:
            raise HTTPException(
                status_code=500,
                detail="OpenAI API key is not configured. Please set the OPENAI_API_KEY environment variable.",
            )

        # Set the OpenAI configuration in environment for the Agents SDK
        import os

        os.environ["OPENAI_API_KEY"] = config.openai_api_key
        # Configure timeout and retry settings for better handling of quota/rate limit issues
        os.environ["OPENAI_TIMEOUT"] = str(config.openai_timeout)
        os.environ["OPENAI_MAX_RETRIES"] = str(config.openai_max_retries)

        # Run the agent workflow using the Orchestrator
        logger.debug("Running agent workflow with Orchestrator")
        # Type ignore: agents SDK accepts dict with role/content but type checker expects TResponseInputItem
        result = await Runner.run(orchestrator_agent, input=agent_input)  # type: ignore

        logger.debug("Agent workflow completed successfully")
        logger.debug(f"Response: {result.final_output}")

        # Create the response
        agent_response = AgentResponse(
            response=result.final_output,
            agent_name="Orchestrator",  # Default to orchestrator, actual agent might be determined by handoff
            success=True,
        )

        logger.debug("Successfully returning response from /agent_response endpoint")
        return JSONResponse(content=jsonable_encoder(agent_response))

    except Exception as e:
        logger.error(f"Error in /agent_response endpoint: {str(e)}")

        # Return error response
        error_response = AgentResponse(
            response=f"Sorry, I encountered an error processing your request: {str(e)}",
            agent_name="Error",
            success=False,
        )
        return JSONResponse(status_code=500, content=jsonable_encoder(error_response))


@router.post("/commute_alert", status_code=201, dependencies=[Depends(verify_token)])
async def store_commute_alert(request: CommuteAlertRequest):
    """
    Store a commute alert to persistent JSON storage.

    This endpoint receives commute alerts from the email sink service
    and stores them in a JSON file for later retrieval.

    Args:
        request: The commute alert data

    Returns:
        Success confirmation with alert ID
    """
    try:
        # Ensure storage directory exists
        storage_dir = Path(config.storage_path)
        storage_dir.mkdir(exist_ok=True)

        # Define the alerts file path
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

        # Create the alert record
        alert_record = {
            "id": f"alert_{len(alerts) + 1}_{request.uid}",
            "uid": request.uid,
            "subject": request.subject,
            "body": request.body,
            "sender": request.sender,
            "received_date": request.date.isoformat(),
            "stored_date": datetime.now().isoformat(),
            "alert_type": request.alert_type,
        }

        # Add to alerts list
        alerts.append(alert_record)

        # Write back to file with proper error handling
        try:
            with open(alerts_file, "w", encoding="utf-8") as f:
                json.dump(alerts, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to write alerts to file: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to store alert to persistent storage"
            )

        logger.info(
            f"Successfully stored commute alert {alert_record['id']} from {request.sender}"
        )

        # Return success response
        response = CommuteAlertResponse(
            success=True,
            message="Alert stored successfully",
            alert_id=alert_record["id"],
        )

        return JSONResponse(content=jsonable_encoder(response))

    except Exception as e:
        logger.error(f"Error in /commute_alert endpoint: {str(e)}")

        # Return error response
        error_response = CommuteAlertResponse(
            success=False, message=f"Failed to store alert: {str(e)}", alert_id=""
        )
        return JSONResponse(status_code=500, content=jsonable_encoder(error_response))


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
