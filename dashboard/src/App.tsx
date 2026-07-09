import { useLiveFlows, useSummary } from "./hooks";
import Header from "./components/Header";
import StatTiles from "./components/StatTiles";
import BandwidthChart from "./components/BandwidthChart";
import FlowTable from "./components/FlowTable";

export default function App() {
  const { flows, connected } = useLiveFlows();
  const summary = useSummary(2000);

  return (
    <div className="app">
      <Header connected={connected} />
      <StatTiles summary={summary} flows={flows} />
      <section className="card">
        <h2>Bandwidth by class</h2>
        <BandwidthChart summary={summary} />
      </section>
      <section className="card">
        <h2>Live flows</h2>
        <FlowTable flows={flows} />
      </section>
    </div>
  );
}
