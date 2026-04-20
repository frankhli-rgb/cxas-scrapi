"""Tests for designer.py."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from cxas_scrapi.migration.designer import AsyncAgentDesigner
from cxas_scrapi.migration.data_models import MigrationIR, IRMetadata

@pytest.fixture
def mock_gemini_client():
    client = MagicMock()
    client.generate_async = AsyncMock()
    return client

@pytest.fixture
def designer(mock_gemini_client):
    return AsyncAgentDesigner(gemini_client=mock_gemini_client)

@pytest.fixture
def sample_ir():
    metadata = IRMetadata(app_name="Test App")
    return MigrationIR(metadata=metadata)

@pytest.mark.asyncio
async def test_run_step_2a_missing_tree_view(designer, sample_ir):
    """Test that run_step_2a raises ValueError when tree_view is missing."""
    with pytest.raises(ValueError) as exc_info:
        await designer.run_step_2a("Test Flow", "", sample_ir)
    assert "tree_view is required" in str(exc_info.value)

@pytest.mark.asyncio
async def test_run_step_2b_missing_tree_view(designer):
    """Test that run_step_2b_instructions raises ValueError when tree_view is missing."""
    with pytest.raises(ValueError) as exc_info:
        await designer.run_step_2b_instructions("Test Flow", {}, "")
    assert "tree_view is required" in str(exc_info.value)

@pytest.mark.asyncio
async def test_run_step_2c_missing_tree_view(designer, sample_ir):
    """Test that run_step_2c_tools_and_callbacks raises ValueError when tree_view is missing."""
    with pytest.raises(ValueError) as exc_info:
        await designer.run_step_2c_tools_and_callbacks("Test Flow", {}, "", sample_ir)
    assert "tree_view is required" in str(exc_info.value)

@pytest.mark.asyncio
async def test_run_step_2a_success(designer, mock_gemini_client, sample_ir):
    """Test successful generation of blueprint."""
    mock_gemini_client.generate_async.return_value = '```json\n{"agent_metadata": {"name": "Test Flow"}}\n```'
    
    blueprint = await designer.run_step_2a("Test Flow", "Dummy Tree View", sample_ir)
    
    assert blueprint == {"agent_metadata": {"name": "Test Flow"}}
    mock_gemini_client.generate_async.assert_called_once()

@pytest.mark.asyncio
async def test_run_step_2b_success(designer, mock_gemini_client):
    """Test successful generation of instructions."""
    mock_gemini_client.generate_async.return_value = '```xml\n<Agent><Name>Test Flow</Name></Agent>\n```'
    
    instructions = await designer.run_step_2b_instructions("Test Flow", {}, "Dummy Tree View")
    
    assert instructions == "<Agent><Name>Test Flow</Name></Agent>"
    mock_gemini_client.generate_async.assert_called_once()

@pytest.mark.asyncio
async def test_run_step_2c_success(designer, mock_gemini_client, sample_ir):
    """Test successful generation of tools and callbacks."""
    mock_gemini_client.generate_async.return_value = '```json\n{"tools": [{"name": "test_tool"}]}\n```'
    
    tools_callbacks = await designer.run_step_2c_tools_and_callbacks("Test Flow", {}, "Dummy Tree View", sample_ir)
    
    assert tools_callbacks == {"tools": [{"name": "test_tool"}]}
    mock_gemini_client.generate_async.assert_called_once()
