import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { StereoMediaSurface } from "./StereoMediaSurface.js";
import { createSyntheticViewerDataSource } from "../../lib/syntheticFixture.js";

describe("StereoMediaSurface", () => {
  it("renders both deterministic cameras from one timestamp with explicit gap state", async () => {
    const dataSource = createSyntheticViewerDataSource();
    const manifest = await dataSource.getSessionManifest("synthetic-stereo");
    const playheadNs = manifest.startNs + 4_500_000_000n;
    const html = renderToStaticMarkup(
      <StereoMediaSurface
        dataSource={dataSource}
        manifest={manifest}
        playheadNs={playheadNs}
        playing={false}
        playbackRate={1}
      />
    );
    expect(html).toContain("camera-left-fixture-media");
    expect(html).toContain("camera-right-fixture-media");
    expect(html.match(/4\.500 s/g)).toHaveLength(2);
    expect(html).toContain("Missing frames · missing");
    expect(html.match(/media-state ready/g)).toHaveLength(2);
  });

  it("keeps stream loading and codec failures independent and visible", async () => {
    const fixture = createSyntheticViewerDataSource();
    const manifest = await fixture.getSessionManifest("synthetic-stereo");
    const dataSource = {
      ...fixture,
      mediaSources: (
        _sessionId: string,
        stream: (typeof manifest.streams)[number]
      ) =>
        stream.id === "camera-left"
          ? [{ src: "fixture://left", synthetic: { label: "LEFT", hue: 164 } }]
          : [
              {
                src: "fixture://right",
                type: "video/x-impossible",
                compatibility: "unsupported" as const
              }
            ]
    };
    const html = renderToStaticMarkup(
      <StereoMediaSurface
        dataSource={dataSource}
        manifest={manifest}
        playheadNs={manifest.startNs}
        playing
        playbackRate={1}
      />
    );
    expect(html).toContain("media-state ready");
    expect(html).toContain("media-state error");
    expect(html).toContain("Unsupported codec or media unavailable");
  });
});
