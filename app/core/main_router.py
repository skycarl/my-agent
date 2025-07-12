from typing import List
from fastapi import APIRouter, HTTPException, Depends
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel
from app.core.auth import verify_token
from app.core.openai_client import openai_client

router = APIRouter()


class Message(BaseModel):
    """Individual message in a conversation."""
    role: str  # "user", "assistant", "system"
    content: str


class ResponsesRequest(BaseModel):
    """Request model for the responses endpoint."""
    messages: List[Message]


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str


@router.get("/healthcheck", status_code=200, response_model=HealthResponse)
def healthcheck():
    """Health check endpoint."""
    logger.debug("Health check endpoint called")
    return HealthResponse(status="healthy")


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
        
        logger.debug(f"Calling OpenAI API with messages: {messages}")
        
        # Call OpenAI API
        response = await openai_client.create_response(messages)
        
        logger.debug(f"OpenAI API response received: {response}")
        
        # Log the response content for debugging
        if isinstance(response, dict) and "choices" in response:
            if len(response["choices"]) > 0:
                response_content = response["choices"][0].get("message", {}).get("content", "")
                logger.debug(f"AI response content: {response_content}")
        
        logger.debug("Successfully returning response from /responses endpoint")
        return JSONResponse(content=jsonable_encoder(response))
    
    except Exception as e:
        logger.info(f"Error in /responses endpoint: {str(e)}")
        logger.debug(f"Full error details: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
