from aeromaint_capture import CaptureClient, ImuSample

assert CaptureClient.__module__ == "aeromaint_capture.client"
assert ImuSample(9_007_199_254_740_993, 1.0, 2.0, 3.0, {}).timestamp_ns == 9_007_199_254_740_993
print("isolated Python SDK import passed")
