import sys
from unittest.mock import MagicMock
sys.modules["google.cloud.ces_v1beta"] = MagicMock()
import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.core.conversation_history import ConversationHistory

@patch("cxas_scrapi.core.conversation_history.AgentServiceClient")
def test_conversation_list(mock_client_cls):
    """Test ConversationHistory.list_conversations."""
    mock_client = mock_client_cls.return_value
    mock_conv = MagicMock()
    mock_conv.name = "projects/p/locations/l/apps/a/conversations/c1"
    
    mock_response = [mock_conv]
    mock_client.list_conversations.return_value = mock_response

    conv_client = ConversationHistory(app_id="projects/p/locations/l/apps/a")
    res = conv_client.list_conversations()
    
    assert len(res) == 1
    assert res[0].name == "projects/p/locations/l/apps/a/conversations/c1"
    mock_client.list_conversations.assert_called_once()

@patch("cxas_scrapi.core.conversation_history.AgentServiceClient")
def test_conversation_get(mock_client_cls):
    """Test ConversationHistory.get_conversation."""
    mock_client = mock_client_cls.return_value
    mock_conv = MagicMock()
    mock_conv.name = "projects/p/locations/l/apps/a/conversations/c1"
    mock_client.get_conversation.return_value = mock_conv

    conv_client = ConversationHistory(app_id="projects/p/locations/l/apps/a")
    res = conv_client.get_conversation("c1")
    
    assert res.name == "projects/p/locations/l/apps/a/conversations/c1"
    # Should prefix with app_id if not present
    mock_client.get_conversation.assert_called_once()

def test_conversation_dict_to_yaml():
    """Test static method conversation_dict_to_yaml."""
    conv_dict = {
        "turns": [
            {
                "user_utterance": {"text": "hi"}
            },
            {
                "agent_utterance": {"messages": [{"text": "hello"}]}
            }
        ]
    }
    
    res = ConversationHistory.conversation_dict_to_yaml(conv_dict)
    assert res["name"] == "Converted_Conversation"
    assert len(res["turns"]) == 2
    assert res["turns"][0] == {"user": "hi"}
    assert res["turns"][1] == {"agent": "hello"}

@patch("cxas_scrapi.core.conversation_history.ConversationHistory.get_conversation")
def test_export_conversation_to_yaml(mock_get_conv):
    """Test ConversationHistory.export_conversation_to_yaml."""
    mock_obj = MagicMock()
    
    # Mock the to_dict method
    with patch("cxas_scrapi.core.conversation_history.type") as mock_type:
        mock_to_dict = MagicMock(return_value={"turns": []})
        mock_type.return_value.to_dict = mock_to_dict
        
        with patch("cxas_scrapi.core.conversation_history.AgentServiceClient"):
            conv_client = ConversationHistory(app_id="projects/p/locations/l/apps/a")
            yaml_str = conv_client.export_conversation_to_yaml("c1")
            assert "name: Converted_Conversation" in yaml_str

@patch("cxas_scrapi.core.conversation_history.types.DeleteConversationRequest")
@patch("cxas_scrapi.core.conversation_history.AgentServiceClient")
def test_delete_conversation(mock_client_cls, mock_req_cls):
    def side_effect(**kwargs):
        m = MagicMock()
        for k, v in kwargs.items():
            setattr(m, k, v)
        return m
    mock_req_cls.side_effect = side_effect
    """Test delete_conversation."""
    mock_client = mock_client_cls.return_value
    
    conv_client = ConversationHistory(app_id="projects/p/locations/l/apps/a")
    conv_client.delete_conversation("c1")
    
    mock_client.delete_conversation.assert_called_once()
    
    # Verify the requested name
    called_request = mock_client.delete_conversation.call_args[1]["request"]
    assert called_request.name == "projects/p/locations/l/apps/a/conversations/c1"
