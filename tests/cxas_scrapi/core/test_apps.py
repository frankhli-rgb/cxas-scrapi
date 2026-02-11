


from cxas_scrapi.core.apps import Apps


import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from cxas_scrapi.core.apps import Apps

@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_list_apps_mock(mock_client_cls):
    """Test Apps.list_apps using mocks."""
    mock_client = mock_client_cls.return_value
    
    mock_app = MagicMock()
    mock_app.display_name = "Test App"
    mock_app.name = "projects/p/locations/l/apps/test-app"
    
    # Mock list_apps response
    mock_response = MagicMock()
    mock_response.apps = [mock_app]
    mock_client.list_apps.return_value = mock_response

    project_id = "mock-project"
    location = "us"
    
    apps_client = Apps(project_id=project_id, location=location)
    apps = apps_client.list_apps()
    
    assert len(apps) == 1
    assert apps[0].display_name == "Test App"
    print("PASS: Mock list_apps verified.")


@patch("cxas_scrapi.core.apps.AgentServiceClient")
def test_get_apps_map(mock_client_cls):
    """Test Apps.get_apps_map using mocks."""
    mock_client = mock_client_cls.return_value
    
    mock_app1 = MagicMock()
    mock_app1.display_name = "Test App 1"
    mock_app1.name = "projects/p/locations/l/apps/test-app-1"
    
    mock_app2 = MagicMock()
    mock_app2.display_name = "Test App 2"
    mock_app2.name = "projects/p/locations/l/apps/test-app-2"
    
    # Mock list_apps response
    mock_response = MagicMock()
    mock_response.apps = [mock_app1, mock_app2]
    mock_client.list_apps.return_value = mock_response

    project_id = "mock-project"
    location = "us"
    
    apps_client = Apps(project_id=project_id, location=location)
    apps_map = apps_client.get_apps_map()
    
    assert len(apps_map) == 2
    assert apps_map["projects/p/locations/l/apps/test-app-1"] == "Test App 1"
    assert apps_map["projects/p/locations/l/apps/test-app-2"] == "Test App 2"
    
    apps_map_reverse = apps_client.get_apps_map(reverse=True)
    assert len(apps_map_reverse) == 2
    assert apps_map_reverse["Test App 1"] == "projects/p/locations/l/apps/test-app-1"
    assert apps_map_reverse["Test App 2"] == "projects/p/locations/l/apps/test-app-2"
