#!/usr/bin/env python3
"""Basic test to verify the application can import and initialize."""

import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from openephys_zmq2osc.config.settings import get_config
from openephys_zmq2osc.core.events.event_bus import get_event_bus, EventType
from openephys_zmq2osc.core.services.data_manager import DataManager
from openephys_zmq2osc.core.services.zmq_service import ZMQService
from openephys_zmq2osc.core.services.osc_service import OSCService


def test_imports():
    """Test that all modules can be imported."""
    print("✅ All imports successful")


def test_config():
    """Test configuration system."""
    config = get_config()
    assert config.app.app_name == "OpenEphys - ZMQ to OSC"
    assert config.zmq.host == "localhost"
    assert config.osc.port == 10000
    print("✅ Configuration system working")


def test_event_bus():
    """Test event bus functionality."""
    event_bus = get_event_bus()
    received_events = []
    
    def test_callback(event):
        received_events.append(event)
    
    # Subscribe and publish test event
    event_bus.subscribe(EventType.SERVICE_STARTED, test_callback)
    event_bus.publish_event(EventType.SERVICE_STARTED, data={"test": True}, source="test")
    
    # Give it a moment
    time.sleep(0.01)
    
    assert len(received_events) == 1
    assert received_events[0].data["test"] == True
    assert received_events[0].source == "test"
    
    event_bus.unsubscribe(EventType.SERVICE_STARTED, test_callback)
    print("✅ Event bus working")


def test_data_manager():
    """Test data manager functionality."""
    dm = DataManager()
    dm.init_empty_buffer(num_channels=4, num_samples=100)
    
    assert dm.num_channels == 4
    assert len(dm.channels) == 4
    
    # Test data push
    import numpy as np
    test_data = np.random.random(50).astype(np.float32)
    dm.push_data(0, test_data)
    
    channel_info = dm.get_channel_info(0)
    assert channel_info['tail_sample_number'] == 50
    
    print("✅ Data manager working")


def test_services_init():
    """Test that services can be initialized."""
    config = get_config()
    
    # Test ZMQ service initialization (don't start it)
    zmq_service = ZMQService(
        ip=config.zmq.host,
        data_port=config.zmq.data_port
    )
    assert zmq_service.ip == "localhost"
    assert zmq_service.data_port == 5556
    
    # Test OSC service initialization (don't start it)
    osc_service = OSCService(
        host=config.osc.host,
        port=config.osc.port
    )
    assert osc_service.host == "127.0.0.1"
    assert osc_service.port == 10000
    
    print("✅ Services can be initialized")


def main():
    """Run all tests."""
    print("Running basic tests...")
    
    test_imports()
    test_config()
    test_event_bus()
    test_data_manager()
    test_services_init()
    
    print("\n🎉 All basic tests passed!")
    print("The application should be ready to run.")


if __name__ == "__main__":
    main()