# Phase 1 Testing Plan

## Pre-Testing Checklist ✅

### 1. Code Validation
- [x] **Settings.py syntax**: Configuration loading works correctly
- [x] **OSC service syntax**: Batching logic compiles without errors
- [x] **Configuration files**: High-throughput and low-latency configs created
- [x] **Batching logic**: Mathematical calculations validated (48x reduction confirmed)
- [x] **Queue overflow**: Logic tested for all three strategies

### 2. Configuration Validation
- [x] **High-throughput config**: Batch size 50, queue limit 50, batching enabled
- [x] **Low-latency config**: Batch size 1, queue limit 10, batching disabled
- [x] **Config loading**: Both configurations load without errors

## Testing Requirements

### Step 1: Rebuild Binary with Phase 1 Changes ⚠️ REQUIRED
The current executable in `dist/` was built **before** Phase 1 optimizations and lacks:
- Performance configuration system
- OSC message batching 
- Queue management improvements
- Enhanced performance monitoring

**Action Required:**
```bash
# Rebuild the binary with new optimizations
python build.py
```

### Step 2: Configuration Testing
Test that the new configurations can be loaded by the updated executable:

```bash
# Test high-throughput config loading
cd dist/
./openephys-zmq2osc-darwin-arm64 --config config_high_throughput.json
# Should show: "OpenEphys - ZMQ to OSC (High Throughput)" in title

# Test low-latency config loading  
./openephys-zmq2osc-darwin-arm64 --config config_low_latency.json
# Should show: "OpenEphys - ZMQ to OSC (Low Latency)" in title
```

### Step 3: Performance Monitoring Validation
With the new executable running, verify the CLI displays:

#### High-Throughput Mode Expected Display:
```
Messages    Sent: 1000 | OSC: 20 | Batch: 50 (50.0x)
            Overflows: 0 | Dropped: 0
```

#### Low-Latency Mode Expected Display:
```  
Messages    Sent: 1000 | OSC: 1000 | Batch: 1 (1.0x)
            Overflows: 0 | Dropped: 0
```

### Step 4: Performance Testing Scenarios

#### Scenario A: Validate Message Reduction (No Real Data Required)
1. Run with high-throughput config
2. Monitor CLI display for batching efficiency
3. Confirm "Batch: 50 (X.Xx)" appears in Messages section
4. Verify no queue overflows occur

#### Scenario B: Queue Management Testing (Optional)
1. Temporarily modify config to very small queue: `"osc_queue_max_size": 2`
2. Run application and monitor for overflows
3. Should see "Overflows: X | Dropped: Y" counters increment
4. Verify system remains stable despite overflows

#### Scenario C: Performance Mode Comparison
1. Run same test with both configurations
2. Compare efficiency displays between modes
3. High-throughput should show 50x efficiency
4. Low-latency should show 1x efficiency (no batching)

## Success Criteria

### ✅ Configuration System
- [ ] High-throughput config loads without errors
- [ ] Low-latency config loads without errors  
- [ ] Application title reflects the configuration mode
- [ ] Performance settings are applied correctly

### ✅ OSC Message Batching
- [ ] High-throughput mode shows "Batch: 50 (X.Xx)" 
- [ ] Low-latency mode shows "Batch: 1 (1.0x)"
- [ ] Efficiency calculations are mathematically correct
- [ ] Batching can be enabled/disabled via configuration

### ✅ Queue Management  
- [ ] Queue size remains bounded in high-throughput mode
- [ ] Overflow counters work when limits are exceeded
- [ ] Application remains stable during overflow conditions
- [ ] Different overflow strategies can be configured

### ✅ Performance Monitoring
- [ ] CLI displays new performance metrics
- [ ] OSC message counts distinguish between logical and actual messages
- [ ] Queue overflow and drop statistics are shown
- [ ] Performance data updates in real-time

## Performance Expectations

### For 32+ Channel Scenarios:
- **Before Phase 1**: 15,360 OSC messages per chunk → Queue growth → System instability
- **After Phase 1**: 307 OSC messages per chunk → Stable queue → System stability

### Expected Improvements:
1. **32 channels**: System should remain stable with bounded queue growth
2. **64 channels**: Should be testable without immediate system overload  
3. **Queue management**: No unbounded growth even under high load
4. **UI responsiveness**: Interface should remain responsive during data processing

## Troubleshooting

### If Binary Rebuild Fails:
- Check that all Phase 1 code changes are syntactically correct
- Verify all imports are working in the Python environment
- Review build.py for any dependency issues

### If Configuration Loading Fails:
- Validate JSON syntax in configuration files
- Check that all new PerformanceConfig fields are properly defined
- Verify Config.from_dict() handles new performance section

### If Performance Metrics Don't Appear:
- Ensure OSC service receives config parameter correctly
- Check that CLI interface updates include new performance fields
- Verify event bus publishes enhanced performance data

## Next Steps After Successful Phase 1 Testing

1. **Document Performance Baseline**: Record actual performance improvements
2. **Identify Remaining Bottlenecks**: Monitor which components still limit performance
3. **Prepare Phase 2 Implementation**: UI throttling and event optimization
4. **Real-World Validation**: Test with actual OpenEphys data if available

---

**Status**: Ready for Testing  
**Prerequisites**: Binary rebuild required  
**Expected Duration**: 30-60 minutes  
**Risk Level**: Low (changes are backward compatible)