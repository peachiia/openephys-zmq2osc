# OpenEphys ZMQ2OSC High-Throughput Optimization Plan

## Problem Analysis

The current implementation faces significant performance bottlenecks when handling high channel counts (>32 channels). Testing shows:
- **16 channels**: Works fine
- **32 channels**: Noticeable delays and queue growth  
- **Higher channel counts**: System becomes unstable

### Core Issue
The OSC sending mechanism is not fast enough for high channel counts, causing cumulative delays and continuous queue growth. The bottleneck manifests as the system struggles to keep up with incoming ZMQ data when channel count exceeds ~32 channels.

## Root Cause Analysis

### Critical Bottlenecks Identified:

#### 1. **OSC Message Transmission (CRITICAL)**
- **Current Behavior**: Sends one OSC message per sample
- **Impact**: For 32 channels × 480 samples/batch = 15,360 individual OSC messages per batch
- **Problems**: 
  - UDP overhead becomes significant
  - Unlimited OSC queue growth
  - Network bandwidth saturation
  - CPU overhead from system calls

#### 2. **Event System Overhead (HIGH)**
- **Current Behavior**: UI updates on every data event
- **Impact**: 
  - Excessive metrics collection (100 delay measurements, 50 sample history)
  - High-frequency event publishing between threads
  - Python GIL contention between threads

#### 3. **Memory Management Inefficiency (MEDIUM)**
- **Current Behavior**: Dynamic allocation and conversion overhead
- **Impact**:
  - No memory pooling or pre-allocation
  - Frequent numpy array conversions (.tolist())
  - Fixed buffer sizes with no adaptive optimization

#### 4. **Configuration Limitations (MEDIUM)**
- **Current Behavior**: Limited performance tuning options
- **Impact**:
  - No batching controls
  - No throughput vs. latency trade-offs
  - No queue management options

## Technical Deep Dive

### Current Data Flow Analysis
```
ZMQ Service → DataManager → Event Bus → OSC Service → Individual UDP Messages
     ↓            ↓           ↓            ↓              ↓
Channel Data → Buffers → Events → Queue → 480 messages/batch
```

### Performance Measurements
- **16 channels**: ~7,680 OSC messages/batch (manageable)
- **32 channels**: ~15,360 OSC messages/batch (borderline)
- **64 channels**: ~30,720 OSC messages/batch (system overload)

### Memory Usage Analysis
- **Current**: ~30MB for 256 channels (256 × 30,000 × 4 bytes)
- **OSC Queue**: Unbounded growth potential (memory leak risk)
- **Overhead**: Event bus and conversion operations

## Optimization Strategy

### Phase 1: Critical Performance Fixes (High Impact, Low Risk)

#### 1.1 OSC Message Batching
**Goal**: Reduce message count by 10-100x
```python
# Current: 1 message per sample
for sample in samples:
    client.send_message("/data", sample)

# Optimized: Batch multiple samples
batch_size = 50
for i in range(0, len(samples), batch_size):
    batch = samples[i:i+batch_size]
    client.send_message("/data/batch", batch)
```
**Expected Impact**: 50x reduction in OSC messages

#### 1.2 Queue Management
**Goal**: Prevent unbounded queue growth
- Add configurable OSC queue size limits (default: 100 batches)
- Implement overflow handling (drop oldest or newest)
- Add queue monitoring and alerting
- Backpressure to ZMQ service when queue is full

#### 1.3 UI Update Throttling
**Goal**: Reduce UI overhead during high-throughput
- Separate data processing from UI refresh
- Batch UI updates (every 100ms instead of per-event)
- Reduce metrics collection frequency during high load

### Phase 2: Memory and Buffer Optimization (Medium Impact, Medium Risk)

#### 2.1 Memory Pool Implementation
**Goal**: Eliminate allocation overhead
```python
class MemoryPool:
    def __init__(self, max_channels=256, buffer_size=30000):
        self.pools = {
            'numpy_arrays': [np.zeros(buffer_size) for _ in range(max_channels)],
            'sample_batches': [np.zeros(100) for _ in range(100)]
        }
```

#### 2.2 Adaptive Buffer Management
**Goal**: Optimize memory usage based on actual load
- Dynamic buffer sizing based on data rates
- Channel grouping for partial processing
- Configurable latency vs. throughput modes

### Phase 3: Advanced Optimizations (High Impact, Higher Risk)

#### 3.1 Network Protocol Optimization
**Goal**: Maximize network efficiency
- Bundle multiple channels per OSC message
- Implement optional compression for high-density data
- Add TCP option for guaranteed delivery in local networks
- Custom binary protocol for maximum throughput

#### 3.2 Event System Redesign
**Goal**: Minimize inter-thread communication overhead
- Reduce event frequency through intelligent batching
- Lock-free data structures where possible
- Priority-based event processing
- Direct memory sharing between threads

#### 3.3 High-Channel Specific Features
**Goal**: Support 256+ channels
- NUMA-awareness for multi-socket systems
- Channel priority and routing systems
- Performance profiling and bottleneck detection
- Automatic performance optimization

### Phase 4: Configuration and Monitoring Enhancements

#### 4.1 Performance Configuration
```json
{
  "performance": {
    "mode": "high_throughput",  // "low_latency", "balanced", "high_throughput"
    "osc_batch_size": 50,
    "queue_max_size": 100,
    "ui_update_interval_ms": 100,
    "metrics_collection_interval_ms": 500
  }
}
```

#### 4.2 Advanced Monitoring
- Real-time performance metrics dashboard
- Bottleneck detection and alerting
- Automatic performance recommendations
- Export performance data for analysis

## Implementation Plan

### Week 1: OSC Batching and Queue Management
**Priority**: CRITICAL
- [ ] Implement OSC message batching in `osc_service.py`
- [ ] Add configurable batch sizes (10, 50, 100 samples)
- [ ] Add queue size limits and overflow handling
- [ ] Test with 32-128 channels
- [ ] Performance benchmarking

**Files to Modify**:
- `src/openephys_zmq2osc/core/services/osc_service.py`
- `src/openephys_zmq2osc/config/settings.py`

### Week 2: UI and Event Optimization  
**Priority**: HIGH
- [ ] Throttle UI updates during high-throughput
- [ ] Reduce metrics collection frequency
- [ ] Optimize event publishing patterns
- [ ] Add performance monitoring
- [ ] Validation testing

**Files to Modify**:
- `src/openephys_zmq2osc/interfaces/cli_interface.py`
- `src/openephys_zmq2osc/core/events/event_bus.py`

### Week 3: Memory and Buffer Optimization
**Priority**: MEDIUM
- [ ] Implement memory pooling for numpy arrays
- [ ] Add adaptive buffer sizing
- [ ] Optimize data conversion overhead
- [ ] Stress testing with 256+ channels

**Files to Modify**:
- `src/openephys_zmq2osc/core/services/data_manager.py`
- New file: `src/openephys_zmq2osc/core/memory/pool_manager.py`

### Week 4: Advanced Features and Polish
**Priority**: LOW
- [ ] Network protocol enhancements
- [ ] Advanced configuration options
- [ ] Performance monitoring dashboard
- [ ] Documentation and deployment guides

## Success Criteria

### Performance Targets:
- **32 channels**: Stable operation with <10ms average delay, queue growth <10 batches
- **64 channels**: Stable operation with <20ms average delay, queue growth <20 batches
- **128 channels**: Functional with acceptable delay (<50ms), stable queue
- **256+ channels**: Experimental support with monitoring and degraded performance

### Quality Metrics:
- Queue growth remains bounded under all loads
- Memory usage grows linearly with channel count (not exponentially)
- UI remains responsive during high-throughput operations
- Configuration allows fine-tuning for different use cases
- System gracefully degrades under overload conditions

### Testing Scenarios:
1. **Sustained Load**: 32 channels for 1 hour continuous operation
2. **Burst Load**: 64 channels with intermittent data
3. **Stress Test**: 128 channels until system limits
4. **Memory Test**: Monitor memory usage over 24 hours
5. **Network Test**: Validate OSC message integrity under load

## Risk Mitigation

### Low-Risk Optimizations (Implement First):
- ✅ Configuration-based batching
- ✅ UI update throttling  
- ✅ Queue size limits
- ✅ Metrics collection reduction

### Medium-Risk Changes (Careful Testing Required):
- ⚠️ Memory pooling implementation
- ⚠️ Event system modifications
- ⚠️ Buffer management changes
- ⚠️ Thread communication optimization

### High-Risk Modifications (Extensive Testing Required):
- ⚠️ Network protocol changes
- ⚠️ Lock-free data structures
- ⚠️ NUMA optimizations
- ⚠️ Custom binary protocols

## Configuration Examples

### High-Throughput Mode (32+ channels)
```json
{
  "performance": {
    "mode": "high_throughput",
    "osc_batch_size": 100,
    "queue_max_size": 50,
    "ui_update_interval_ms": 200,
    "memory_preallocation": true
  }
}
```

### Low-Latency Mode (1-16 channels)
```json
{
  "performance": {
    "mode": "low_latency", 
    "osc_batch_size": 1,
    "queue_max_size": 10,
    "ui_update_interval_ms": 50,
    "memory_preallocation": false
  }
}
```

## Monitoring and Debugging

### Key Metrics to Track:
- OSC queue size and growth rate
- Message transmission rate (messages/second)
- Average end-to-end latency
- Memory usage per channel
- CPU utilization per thread
- Network bandwidth utilization

### Debug Tools to Implement:
- Real-time performance dashboard
- Queue overflow alerts
- Automatic performance mode switching
- Export performance data to CSV/JSON
- Visual performance graphs in CLI

## Future Considerations

### Scalability Beyond 256 Channels:
- Consider switching to binary protocols (MessagePack, Protocol Buffers)
- Implement data compression (LZ4, Snappy)
- Use memory-mapped files for inter-process communication
- Consider multi-process architecture for CPU-bound operations

### Integration Considerations:
- Maintain backward compatibility with existing OSC clients
- Provide migration tools for configuration updates
- Ensure graceful degradation when limits are reached
- Document performance characteristics for different scenarios

---

**Document Version**: 1.0  
**Created**: 2025-01-22  
**Last Updated**: 2025-01-22  
**Status**: Implementation Ready