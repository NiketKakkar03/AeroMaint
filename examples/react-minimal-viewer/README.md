# Minimal React viewer

This reference component consumes only the packed `@aeromaint/capture-sdk` interface. It pages sessions, loads manifest-declared authenticated media into a `<video>`, derives the canonical nanosecond playhead from relative `currentTime`, displays a one-second IMU window, and creates/refreshes an export job.

Install `@aeromaint/react-minimal-viewer`, its SDK dependency, and React 19, then render:

```tsx
<MinimalViewer baseUrl="http://localhost:8000" token={token} />
```

Production callers should provide a short-lived read/export token. Network, API, media decoding, and export failures are surfaced in the alert. The example intentionally never converts an absolute nanosecond timestamp to a JavaScript `number`.
