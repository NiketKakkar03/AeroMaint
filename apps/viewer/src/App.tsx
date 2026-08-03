const platformLayers = [
  ["Capture", "EuRoC, ROS 2, and MCAP adapters"],
  ["Platform", "Versioned contracts, range APIs, and SDKs"],
  ["Viewer", "Synchronized video, sensor tracks, and annotations"],
  ["Intelligence", "Deterministic ML, retrieval, and reviewed recommendations"]
] as const;

export function App() {
  return (
    <main>
      <header>
        <span className="eyebrow">AeroMaint Studio / Initial platform</span>
        <h1>Engineering data, synchronized.</h1>
        <p className="intro">
          A local-first workspace for inspecting multimodal aerospace capture
          sessions and building evidence-backed engineering workflows.
        </p>
        <div className="status">
          <span aria-hidden="true" /> Platform scaffold ready
        </div>
      </header>

      <section aria-labelledby="architecture-heading">
        <div className="section-heading">
          <p>Foundation</p>
          <h2 id="architecture-heading">Platform-first architecture</h2>
        </div>
        <div className="grid">
          {platformLayers.map(([title, description], index) => (
            <article key={title}>
              <span>0{index + 1}</span>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <aside>
        Educational decision-support prototype. Not approved for vehicle control
        or aircraft maintenance.
      </aside>
    </main>
  );
}
