from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel
from app.core.auth import verify_token
from app.core.openai_client import openai_client
from app.core.settings import config

router = APIRouter()


class Message(BaseModel):
    """Individual message in a conversation."""
    role: str  # "user", "assistant", "system"
    content: str


class ResponsesRequest(BaseModel):
    """Request model for the responses endpoint."""
    messages: List[Message]
    model: Optional[str] = None  # Optional model override


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str


class ModelsResponse(BaseModel):
    """Models endpoint response model."""
    models: list[str]
    default_model: str = "gpt-4o"


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
        models=config.valid_openai_models,
        default_model="gpt-4o"
    )


@router.post("/responses", status_code=200, dependencies=[Depends(verify_token)])
async def create_response(request: ResponsesRequest):
    """
    Create a response using OpenAI's Responses API with message history.
    
    Args:
        request: The request containing the message history
        
    Returns:
        The OpenAI response
    """
    try:
        logger.debug(f"Received request to /responses endpoint with {len(request.messages)} messages")
        
        # Log the incoming messages for debugging
        for i, message in enumerate(request.messages):
            logger.debug(f"Message {i+1}: role={message.role}, content={message.content}")
        
        # Convert Pydantic models to dict format expected by OpenAI
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

        # Determine which model to use (default to gpt-4o)
        model = request.model or "gpt-4o"
        logger.debug(f"Using model '{model}' for this request")
        
        # Validate the model
        if model not in config.valid_openai_models:
            logger.warning(f"Invalid model requested: {model}")
            raise HTTPException(
                status_code=400, 
                detail=f"Invalid model '{model}'. Available models: {', '.join(config.valid_openai_models)}"
            )
        
        logger.debug(f"Calling OpenAI API with messages: {messages}")
        
        # Call OpenAI API
        response = await openai_client.create_response(messages, model=model)
        
        logger.debug(f"OpenAI API response received: {response}")
        
        # Log the response content for debugging
        if isinstance(response, dict) and "choices" in response:
            if len(response["choices"]) > 0:
                response_content = response["choices"][0].get("message", {}).get("content", "")
                logger.debug(f"AI response content: {response_content}")
        
        logger.debug("Successfully returning response from /responses endpoint")
        return JSONResponse(content=jsonable_encoder(response))
    
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.info(f"Error in /responses endpoint: {str(e)}")
        logger.debug(f"Full error details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
