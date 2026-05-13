import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LinearScale,
  Title,
  Tooltip,
} from "chart.js";
import { Bar, Doughnut } from "react-chartjs-2";
import { useData } from "../context/DataContext";

ChartJS.register(CategoryScale, LinearScale, BarElement, ArcElement, Title, Tooltip, Legend);

const TIER_COLORS: Record<string, string> = {
  Platinum: "rgba(149, 213, 178, 0.88)",
  Gold: "rgba(233, 196, 106, 0.9)",
  Silver: "rgba(154, 163, 181, 0.88)",
  Bronze: "rgba(205, 127, 50, 0.88)",
  Restricted: "rgba(231, 111, 81, 0.85)",
};

const axisStyle = {
  grid: { color: "rgba(37, 42, 54, 0.95)" },
  ticks: { color: "#9aa3b5" },
  border: { color: "#353d52" },
};

export function DashboardCharts() {
  const { users, recentEvents } = useData();

  const sorted = [...users].sort((a, b) => Number(b.score) - Number(a.score));
  const tierCounts: Record<string, number> = {};
  for (const u of users) {
    const t = u.tier || "Silver";
    tierCounts[t] = (tierCounts[t] || 0) + 1;
  }
  const tierLabels = Object.keys(tierCounts).sort();

  const evCounts: Record<string, number> = {};
  for (const ev of recentEvents) {
    const t = ev.event_type || "?";
    evCounts[t] = (evCounts[t] || 0) + 1;
  }
  const evLabels = Object.keys(evCounts).sort((a, b) => evCounts[b] - evCounts[a]);

  const hasUsers = sorted.length > 0;
  const hasEv = evLabels.length > 0;

  return (
    <article className="card wide charts-card">
      <h2>Overview charts</h2>
      <p className="muted small">
        Built from the same data as the tables below (users + loaded recent events).
      </p>
      <div className="charts-grid">
        <div className="chart-panel">
          <h3 className="subh">Behaviour scores by user</h3>
          {hasUsers ? (
            <div className="chart-canvas-wrap" id="wrap-chart-scores">
              <Bar
                data={{
                  labels: sorted.map((u) => u.user_id),
                  datasets: [
                    {
                      label: "Score",
                      data: sorted.map((u) => Number(u.score)),
                      backgroundColor: "rgba(77, 124, 248, 0.5)",
                      borderColor: "rgba(119, 156, 250, 0.95)",
                      borderWidth: 1,
                      borderRadius: 4,
                    },
                  ],
                }}
                options={{
                  indexAxis: "y",
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: { legend: { display: false } },
                  scales: {
                    x: {
                      ...axisStyle,
                      title: {
                        display: true,
                        text: "Behaviour score",
                        color: "#9aa3b5",
                        font: { size: 11 },
                      },
                    },
                    y: {
                      grid: { display: false },
                      ticks: { color: "#c7cfdf" },
                      border: { display: false },
                    },
                  },
                }}
              />
            </div>
          ) : (
            <p className="muted small chart-fallback">No users yet.</p>
          )}
        </div>
        <div className="chart-panel">
          <h3 className="subh">Tier mix</h3>
          {hasUsers ? (
            <div className="chart-canvas-wrap chart-canvas-wrap--compact" id="wrap-chart-tiers">
              <Doughnut
                data={{
                  labels: tierLabels,
                  datasets: [
                    {
                      data: tierLabels.map((l) => tierCounts[l]),
                      backgroundColor: tierLabels.map(
                        (l) => TIER_COLORS[l] || "rgba(100, 116, 139, 0.75)",
                      ),
                      borderColor: "#171b24",
                      borderWidth: 2,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: {
                      position: "bottom",
                      labels: { color: "#c7cfdf", boxWidth: 12, padding: 12 },
                    },
                  },
                }}
              />
            </div>
          ) : (
            <p className="muted small chart-fallback">No users yet.</p>
          )}
        </div>
        <div className="chart-panel chart-span-full">
          <h3 className="subh">Recent events by type</h3>
          {hasEv ? (
            <div className="chart-canvas-wrap" id="wrap-chart-events">
              <Bar
                data={{
                  labels: evLabels,
                  datasets: [
                    {
                      label: "Count",
                      data: evLabels.map((l) => evCounts[l]),
                      backgroundColor: "rgba(61, 168, 126, 0.45)",
                      borderColor: "rgba(94, 196, 154, 0.95)",
                      borderWidth: 1,
                      borderRadius: 4,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: { legend: { display: false } },
                  scales: {
                    x: {
                      grid: { display: false },
                      ticks: { color: "#9aa3b5", maxRotation: 40, minRotation: 40 },
                      border: { color: "#353d52" },
                    },
                    y: {
                      ...axisStyle,
                      title: {
                        display: true,
                        text: "Count",
                        color: "#9aa3b5",
                        font: { size: 11 },
                      },
                    },
                  },
                }}
              />
            </div>
          ) : (
            <p className="muted small chart-fallback">No events in the loaded window.</p>
          )}
        </div>
      </div>
    </article>
  );
}
