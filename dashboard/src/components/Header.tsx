export default function Header({ connected }: { connected: boolean }) {
  return (
    <header className="header">
      <div>
        <h1>Tiresias</h1>
        <div className="subtitle">
          Real-time encrypted-traffic classifier — flow metadata only, no payload inspection
        </div>
      </div>
      <span className="conn">
        <span className={`dot ${connected ? "on" : "off"}`} aria-hidden />
        {connected ? "Live" : "Reconnecting…"}
      </span>
    </header>
  );
}
