import asyncio
import json
import os
import re
from pathlib import Path
from typing import List, Optional

from agents import Runner, RunConfig, set_default_openai_client
from openai import AsyncOpenAI
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel

from app.agents.orchestrator_agent import create_orchestrator_agent
from app.agents.alert_processor_agent import create_alert_processor_agent
from app.core import agent_response_handler
from app.core.agent_response_handler import AgentResponseHandler
from app.core.auth import verify_token
from app.core.conversation_context import set_conversation_id
from app.core.session_manager import get_session, clear_session
from app.core.scheduler import scheduler_service
from app.core.settings import config
from app.core.task_store import (
    append_task_to_config,
    list_tasks_from_config,
    delete_task_by_id,
)
from app.core.task_manager import ALLOWED_TASK_ENDPOINTS
from app.models.tasks import TaskSchedule, APICallConfig
from app.core import telegram_client
from app.core.timezone_utils import now_local
from app.models.tasks import (
    AgentProcessingMetadata,
    AlertRequest,
    AlertResponse,
    TelegramMessageRequest,
    TelegramMessageResponse,
)

os.environ["OPENAI_API_KEY"] = config.openai_api_key
# Timeout/retries are constructor-only params (the SDK never reads them from
# env vars), so register a configured client with the Agents SDK.
set_default_openai_client(
    AsyncOpenAI(
        api_key=config.openai_api_key,
        timeout=config.openai_timeout,
        max_retries=config.openai_max_retries,
    )
)

router = APIRouter()

# Per-conversation locks so concurrent /agent_response requests for the same
# conversation serialize (two Runner.run calls sharing one SQLite session would
# interleave history). Different conversations stay concurrent.
_conversation_locks: dict[str, asyncio.Lock] = {}


def _get_conversation_lock(conversation_id: str) -> asyncio.Lock:
    lock = _conversation_locks.get(conversation_id)
    if lock is None:
        lock = asyncio.Lock()
        _conversation_locks[conversation_id] = lock
    return lock


# UIDs currently being processed by /process_alert, so a re-POST of the same
# alert (e.g. email-sink client timeout) can't trigger a second agent run.
_alert_uids_in_flight: set[str] = set()


def _sanitize_alert_body(body: str, max_length: int = 2000) -> str:
    """Strip URLs, HTML tags, and truncate body for safe agent processing."""
    body = re.sub(r"https?://\S+", "[link removed]", body)
    body = re.sub(r"<[^>]+>", "", body)
    body = body[:max_length]
    return body.strip()


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
    image_base64: Optional[str] = None  # Optional base64-encoded image
    conversation_id: Optional[str] = (
        None  # Conversation (Telegram chat_id) this message belongs to
    )

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


@router.get(
    "/models",
    status_code=200,
    dependencies=[Depends(verify_token)],
    response_model=ModelsResponse,
)
def get_models():
    """Get list of available OpenAI models."""
    logger.debug("Models endpoint called")
    return ModelsResponse(
        models=config.valid_openai_models, default_model=config.default_model
    )


# -----------------------
# Tasks Management
# -----------------------


class NewTaskRequest(BaseModel):
    """Flexible request to add a scheduled task (cron, interval, or date)."""

    id: Optional[str] = None
    name: str
    type: str
    mode: str = "agent"
    enabled: bool = True
    description: Optional[str] = None
    schedule: dict
    api_call: Optional[dict] = None
    notification: Optional[dict] = None
    conversation_id: Optional[str] = None
    max_retries: Optional[int] = None
    retry_delay: Optional[int] = None


class NewTaskResponse(BaseModel):
    success: bool
    message: str
    task_id: str


@router.post(
    "/tasks",
    status_code=201,
    dependencies=[Depends(verify_token)],
    response_model=NewTaskResponse,
)
async def add_task(request: NewTaskRequest):
    """
    Add a new scheduled task (supports cron, interval, and one-time date schedules).

    Automatically triggers a scheduler reload after writing to storage.
    """
    try:
        # Convert request to dict, filter out None values
        task_data = {k: v for k, v in request.model_dump().items() if v is not None}

        # Validate mode
        mode = task_data.get("mode", "agent")
        if mode not in ("agent", "notify"):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid mode: '{mode}'. Must be 'agent' or 'notify'.",
            )

        # Validate schedule against Pydantic model before persisting
        try:
            TaskSchedule(**task_data.get("schedule", {}))
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Invalid schedule: {e}")

        if mode == "notify":
            # Notify mode requires notification config with a message
            notification = task_data.get("notification")
            if not notification or not notification.get("message"):
                raise HTTPException(
                    status_code=422,
                    detail="notification.message is required for notify mode",
                )
        else:
            # Agent mode: validate api_call and enforce endpoint allowlist
            if task_data.get("api_call"):
                try:
                    api_call = APICallConfig(**task_data["api_call"])
                except Exception as e:
                    raise HTTPException(
                        status_code=422, detail=f"Invalid api_call: {e}"
                    )
                normalized = "/" + api_call.endpoint.lstrip("/")
                if normalized not in ALLOWED_TASK_ENDPOINTS:
                    raise HTTPException(
                        status_code=422,
                        detail=f"Endpoint not allowed: {api_call.endpoint}. Allowed: {', '.join(sorted(ALLOWED_TASK_ENDPOINTS))}",
                    )

        # Validate cron expression if applicable
        if task_data.get("schedule", {}).get("type") == "cron":
            from croniter import croniter

            expr = task_data["schedule"].get("expression", "")
            if not croniter.is_valid(expr):
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid cron expression: {expr}",
                )

        # Append to config and reload
        task_id = append_task_to_config(task_data)
        if not scheduler_service.reload_configuration():
            logger.error(f"Scheduler reload failed after adding task {task_id}")
            raise HTTPException(
                status_code=500,
                detail="Task was stored but the scheduler failed to reload; check server logs",
            )

        return NewTaskResponse(
            success=True, message="Task added and scheduler reloaded", task_id=task_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding new task: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add task: {e}")


class ListTasksResponse(BaseModel):
    success: bool
    tasks: list[dict]
    message: str


@router.get(
    "/tasks",
    status_code=200,
    dependencies=[Depends(verify_token)],
)
async def list_tasks(only_enabled: bool = False, name_filter: Optional[str] = None):
    """List scheduled tasks from configuration storage."""
    try:
        tasks = list_tasks_from_config(
            only_enabled=only_enabled, name_filter=name_filter
        )

        # Minimize sensitive data: omit headers if present
        sanitized: list[dict] = []
        for t in tasks:
            t_copy = dict(t)
            api = t_copy.get("api_call")
            if isinstance(api, dict) and "headers" in api:
                api = dict(api)
                api.pop("headers", None)
                t_copy["api_call"] = api
            sanitized.append(t_copy)

        return JSONResponse(
            content=jsonable_encoder(
                ListTasksResponse(success=True, tasks=sanitized, message="OK")
            )
        )
    except Exception as e:
        logger.error(f"Error listing tasks: {e}")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                ListTasksResponse(
                    success=False, tasks=[], message=f"Failed to list tasks: {e}"
                )
            ),
        )


class DeleteTaskResponse(BaseModel):
    success: bool
    task_id: str
    message: str


@router.delete(
    "/tasks/{task_id}",
    status_code=200,
    dependencies=[Depends(verify_token)],
)
async def delete_task(task_id: str):
    """Delete a scheduled task by ID and reload the scheduler."""
    try:
        removed = delete_task_by_id(task_id)
        if not removed:
            return JSONResponse(
                status_code=404,
                content=jsonable_encoder(
                    DeleteTaskResponse(
                        success=False, task_id=task_id, message="Task not found"
                    )
                ),
            )

        scheduler_service.reload_configuration()
        return JSONResponse(
            content=jsonable_encoder(
                DeleteTaskResponse(
                    success=True,
                    task_id=task_id,
                    message="Task deleted and scheduler reloaded",
                )
            )
        )
    except Exception as e:
        logger.error(f"Error deleting task {task_id}: {e}")
        return JSONResponse(
            status_code=500,
            content=jsonable_encoder(
                DeleteTaskResponse(
                    success=False,
                    task_id=task_id,
                    message=f"Failed to delete task: {e}",
                )
            ),
        )


@router.post("/agent_response", status_code=200, dependencies=[Depends(verify_token)])
async def create_agent_response(request_body: AgentRequest, request: Request):
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
        # Extract user message from request
        if request_body.input is not None:
            user_message = request_body.input
            logger.debug(f"Received single input request: {request_body.input}")
        elif request_body.messages is not None and len(request_body.messages) > 0:
            # Take the last message as the new user input
            user_message = request_body.messages[-1].content
            logger.debug(
                f"Received conversation with {len(request_body.messages)} messages, processing last message"
            )
        else:
            raise HTTPException(status_code=400, detail="No input or messages provided")

        # Resolve the conversation this request belongs to (Telegram chat_id as a
        # string). Falls back to the owner when unspecified (e.g. legacy tasks).
        conversation_id = request_body.conversation_id or str(config.owner_user_id)
        set_conversation_id(conversation_id)

        # Determine which model to use (default to config default for agents)
        model = request_body.model or config.default_model
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

        # Build agent input — multimodal when image is present
        if request_body.image_base64:
            agent_input = [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": user_message},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/jpeg;base64,{request_body.image_base64}",
                        },
                    ],
                }
            ]
        else:
            agent_input = user_message

        # Run the agent workflow using the Orchestrator with SDK session
        # The session automatically persists full conversation state
        # (including tool calls, results, and handoff context)
        logger.debug("Running agent workflow with Orchestrator")
        is_scheduled = request.headers.get("X-Scheduled-Task") == "true"

        # Serialize runs per conversation: a second message arriving while the
        # first run is in flight would otherwise share the same SQLite session
        # concurrently and interleave history.
        async with _get_conversation_lock(conversation_id):
            if is_scheduled:
                logger.debug(
                    "Scheduled task invocation — running without conversation session"
                )
                result = await Runner.run(
                    orchestrator_agent,
                    input=agent_input,
                    max_turns=10,
                    run_config=RunConfig(workflow_name="scheduled_task"),
                )
            else:
                session = get_session(conversation_id)
                result = await Runner.run(
                    orchestrator_agent,
                    input=agent_input,
                    session=session,
                    max_turns=10,
                    run_config=RunConfig(workflow_name="agent_response"),
                )

        logger.debug("Agent workflow completed successfully")
        logger.debug(f"Response: {result.final_output}")

        # Process agent response through unified handler
        (
            should_respond,
            response_message,
        ) = await agent_response_handler.AgentResponseHandler.process_user_query_response(
            response=result.final_output, conversation_id=conversation_id
        )

        send_success = False
        telegram_message_id = None

        if should_respond and response_message.strip():
            # Send response directly to the originating conversation via Telegram
            try:
                target_user_id = int(conversation_id) if conversation_id else None
                if target_user_id:
                    (
                        success,
                        message_id,
                    ) = await telegram_client.telegram_client.send_message(
                        user_id=target_user_id,
                        message=response_message,
                        markdown=True,
                    )

                    if success:
                        logger.info(
                            "Successfully sent agent response to user via Telegram"
                        )
                        send_success = True
                        telegram_message_id = message_id
                    else:
                        logger.warning(
                            "Failed to send agent response to user via Telegram"
                        )
                else:
                    logger.warning(
                        "No conversation target resolved for sending response"
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
                "response_sent": send_success,
                "response_text": response_message if should_respond else "",
                "telegram_message_id": telegram_message_id,
            }
        )

    except HTTPException:
        # Intentional 4xx/5xx (e.g. invalid model) — return it as-is instead
        # of converting to a generic 500 with a spurious Telegram error DM.
        raise
    except Exception as e:
        logger.error(f"Error in /agent_response endpoint: {str(e)}")

        # Send error message back to the originating conversation via Telegram
        try:
            conversation_id = request_body.conversation_id or str(config.owner_user_id)
            target_user_id = int(conversation_id) if conversation_id else None
            if target_user_id:
                error_message = (
                    f"Sorry, I encountered an error processing your request: {str(e)}"
                )
                # Plain text: exception text can contain <, >, & that would
                # make Telegram reject an HTML-parsed message.
                await telegram_client.telegram_client.send_message(
                    user_id=target_user_id,
                    message=error_message,
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
    uid_marked_in_flight = False

    try:
        # Load existing alerts early for dedup check
        alerts_file = Path(config.commute_alerts_path)
        alerts_file.parent.mkdir(exist_ok=True)

        alerts = []
        if alerts_file.exists():
            try:
                with open(alerts_file, "r", encoding="utf-8") as f:
                    alerts = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logger.warning(f"Error reading existing alerts file: {e}")
                alerts = []

        # UID deduplication check (.get: a single legacy record without a uid
        # must not 500 every future alert). The in-flight set catches the same
        # UID being re-POSTed while a slow agent run is still processing it.
        existing_uids = {alert.get("uid") for alert in alerts}
        if request.uid in existing_uids or request.uid in _alert_uids_in_flight:
            logger.info(f"Duplicate alert UID {request.uid}, skipping processing")
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Duplicate alert, already processed",
                    "alert_id": "",
                },
            )
        _alert_uids_in_flight.add(request.uid)
        uid_marked_in_flight = True

        # Sender allowlist validation
        allowed_patterns = [
            p.strip() for p in config.email_sender_patterns.split(",") if p.strip()
        ]
        if allowed_patterns and not any(
            pattern in request.sender for pattern in allowed_patterns
        ):
            logger.warning(f"Alert from unauthorized sender: {request.sender}")
            raise HTTPException(status_code=403, detail="Sender not in allowlist")

        # Sanitize body for agent processing (preserve original for storage)
        sanitized_body = _sanitize_alert_body(request.body)

        # Format alert as instructions for the orchestrator agent
        alert_data = {
            "uid": request.uid,
            "subject": request.subject,
            "body": sanitized_body,
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

        # Track agent decision for structured storage on the alert record
        decision = None

        # Inject commute context for schedule-aware filtering
        from app.agents.commute.preferences_service import get_full_commute_context

        commute_context = get_full_commute_context()

        # Create dedicated alert processor agent
        logger.debug("Creating alert processor agent for alert processing")
        alert_agent = create_alert_processor_agent(commute_context=commute_context)

        # Process alert through dedicated alert processor agent
        try:
            result = await Runner.run(
                alert_agent,
                input=agent_input,
                max_turns=5,
                run_config=RunConfig(workflow_name="process_alert"),
            )

            # Extract agent processing metadata
            processing_time = (now_local() - start_time).total_seconds() * 1000
            agent_metadata.success = True
            agent_metadata.agent_response = str(result.final_output)
            agent_metadata.processing_time_ms = int(processing_time)
            agent_metadata.primary_agent = result.last_agent.name

            # result.final_output is an AlertDecision (structured output)
            decision = result.final_output

            if decision.notify_user and decision.message_content.strip():
                # Send notification via Telegram
                sanitized_message = AgentResponseHandler._sanitize_telegram_html(
                    decision.message_content
                )
                (
                    success,
                    message_id,
                ) = await telegram_client.telegram_client.send_message(
                    user_id=config.owner_user_id,
                    message=sanitized_message,
                    parse_mode="HTML",
                )

                if success:
                    agent_metadata.actions_taken = [
                        "alert_processed",
                        "notification_sent",
                    ]
                    logger.info(
                        f"Successfully processed alert {request.uid} and sent notification"
                    )
                else:
                    agent_metadata.actions_taken = [
                        "alert_processed",
                        "notification_failed",
                    ]
                    logger.warning(
                        f"Alert {request.uid} processed but notification send failed"
                    )
            else:
                agent_metadata.actions_taken = [
                    "alert_processed",
                    "notification_not_needed",
                ]
                logger.info(
                    f"Agent determined no notification needed for alert {request.uid}: {decision.rationale}"
                )

            logger.info(f"Successfully processed alert {request.uid} through agents")
            logger.debug(f"Agent decision: {decision}")

        except Exception as e:
            processing_time = (now_local() - start_time).total_seconds() * 1000
            agent_metadata.success = False
            agent_metadata.error_message = f"Agent processing failed: {str(e)}"
            agent_metadata.processing_time_ms = int(processing_time)

            logger.error(f"Agent processing failed for alert {request.uid}: {e}")
            # Continue to store the alert even if agent processing failed

        # Re-read the alerts file before mutating: the agent run above can
        # take seconds, and another alert or the daily cleanup may have
        # written the file in the meantime. There are no awaits between this
        # read and the write below, so the read-modify-write is not
        # interleaved with other event-loop work.
        if alerts_file.exists():
            try:
                with open(alerts_file, "r", encoding="utf-8") as f:
                    alerts = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError) as e:
                logger.warning(f"Error re-reading alerts file before write: {e}")

        # Re-check dedup after the slow agent run: if another request stored
        # this UID in the meantime, don't write a second record.
        if request.uid in {alert.get("uid") for alert in alerts}:
            logger.info(
                f"Alert UID {request.uid} was stored by a concurrent request, skipping store"
            )
            return JSONResponse(
                status_code=200,
                content={
                    "success": True,
                    "message": "Duplicate alert, already processed",
                    "alert_id": "",
                },
            )

        # Create the alert record with agent metadata (uses original body)
        alert_record = {
            "id": f"alert_{len(alerts) + 1}_{request.uid}",
            "uid": request.uid,
            "subject": request.subject,
            "body": request.body,
            "sender": request.sender,
            "received_date": request.date.isoformat(),
            "stored_date": now_local().isoformat(),
            "alert_type": request.alert_type,
            "notify_user": decision.notify_user if decision else False,
            "message_content": decision.message_content if decision else "",
            "rationale": decision.rationale if decision else "",
            "agent_processing": agent_metadata.model_dump(),
            "status": "active",
        }

        # If this alert resolves an earlier one, mark the original as resolved
        if decision and decision.resolves_alert_id:
            alert_record["resolves_alert_id"] = decision.resolves_alert_id
            # A cancellation notice is not an active disruption itself —
            # otherwise "all clear" records show up as active alerts forever
            alert_record["status"] = "resolved"
            for existing_alert in alerts:
                if existing_alert.get("id") == decision.resolves_alert_id:
                    existing_alert["status"] = "resolved"
                    existing_alert["resolved_by"] = alert_record["id"]
                    existing_alert["resolved_date"] = now_local().isoformat()
                    logger.info(
                        f"Alert {decision.resolves_alert_id} marked as resolved by {alert_record['id']}"
                    )
                    break

        # Add to alerts list and cap at 200 most recent
        alerts.append(alert_record)
        if len(alerts) > 200:
            alerts = alerts[-200:]

        # Write back atomically (temp file + rename) so a crash mid-write
        # can't leave a truncated file behind
        try:
            tmp_file = alerts_file.with_suffix(".json.tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(alerts, f, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp_file, alerts_file)
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

    except HTTPException:
        # Intentional status codes (403 sender not allowed, 500 storage
        # failure) — let FastAPI return them instead of masking as a
        # generic 500.
        raise
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
    finally:
        if uid_marked_in_flight:
            _alert_uids_in_flight.discard(request.uid)


class ClearConversationRequest(BaseModel):
    """Request model for clearing a single conversation."""

    conversation_id: Optional[str] = None


@router.post(
    "/clear_conversation", status_code=200, dependencies=[Depends(verify_token)]
)
async def clear_conversation(request_body: Optional[ClearConversationRequest] = None):
    """
    Clear conversation history for a single conversation.

    This endpoint is called by the Telegram bot when a user uses the /clear command.
    When no conversation_id is provided, the owner's conversation is cleared.

    Returns:
        Success confirmation
    """
    try:
        conversation_id = (
            request_body.conversation_id if request_body else None
        ) or str(config.owner_user_id)
        await clear_session(conversation_id)

        logger.info(f"Successfully cleared conversation history for {conversation_id}")
        return JSONResponse(
            content={
                "success": True,
                "message": "Conversation history cleared successfully",
            }
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
        # Determine target user ID
        target_user_id = request.user_id or config.owner_user_id

        if not target_user_id:
            raise HTTPException(
                status_code=400,
                detail="No target user specified and no owner configured",
            )

        logger.debug(
            f"Sending Telegram message to user {target_user_id}: {request.message}"
        )

        # Send the message
        success, message_id = await telegram_client.telegram_client.send_message(
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
