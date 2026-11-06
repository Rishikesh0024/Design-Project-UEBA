import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card } from "./common";

const COLORS = ["#4c7cf3", "#34b48a", "#e7a943", "#a57bf3", "#e56d7e", "#69a8cc"];

export type ActivityPoint = { date: string; activity: string; count: number };

export function ActivityChart({ data }: { data: ActivityPoint[] }) {
  const names = [...new Set(data.map((row) => row.activity))];
  const grouped = Object.values(
    data.reduce<Record<string, Record<string, string | number>>>((acc, row) => {
      acc[row.date] ??= { date: row.date };
      acc[row.date][row.activity] = row.count;
      return acc;
    }, {}),
  );
  return (
    <Card title="Behaviour activity" description="Daily event volume by observed activity type">
      {grouped.length ? (
        <div className="chart-wrap">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={grouped} margin={{ left: -18, right: 6, top: 10 }}>
              <defs>
                {names.map((name, index) => (
                  <linearGradient id={`fill-${index}`} key={name} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={COLORS[index % COLORS.length]} stopOpacity={0.22} />
                    <stop offset="95%" stopColor={COLORS[index % COLORS.length]} stopOpacity={0.01} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid stroke="#edf1f7" vertical={false} />
              <XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fill: "#8290a5", fontSize: 11 }} />
              <YAxis tickLine={false} axisLine={false} tick={{ fill: "#8290a5", fontSize: 11 }} />
              <Tooltip />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
              {names.map((name, index) => (
                <Area
                  key={name}
                  type="monotone"
                  dataKey={name}
                  stackId="1"
                  stroke={COLORS[index % COLORS.length]}
                  fill={`url(#fill-${index})`}
                  strokeWidth={2}
                  connectNulls
                />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : <div className="chart-empty">Activity timeline appears when events are ingested.</div>}
    </Card>
  );
}

export function ActivityBreakdown({ data }: { data: ActivityPoint[] }) {
  const counts = Object.values(data.reduce<Record<string, { name: string; value: number }>>(
    (acc, row) => {
      acc[row.activity] ??= { name: row.activity, value: 0 };
      acc[row.activity].value += row.count;
      return acc;
    }, {},
  ));
  return (
    <Card title="Activity mix" description="Distribution across event types">
      <div className="chart-wrap donut-wrap">
        {counts.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={counts} dataKey="value" nameKey="name" innerRadius={56} outerRadius={82} paddingAngle={3}>
                {counts.map((item, index) => <Cell key={item.name} fill={COLORS[index % COLORS.length]} />)}
              </Pie>
              <Tooltip />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        ) : <div className="chart-empty">No activity records</div>}
      </div>
    </Card>
  );
}

export function RiskChart({ data }: { data: { window_date: string; risk_score: number; threshold_value: number }[] }) {
  return (
    <Card title="Risk score distribution" description="Held-out user-day scores and calibrated thresholds">
      <div className="chart-wrap">
        {data.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.slice(0, 40)} margin={{ left: -18, right: 6, top: 10 }}>
              <CartesianGrid stroke="#edf1f7" vertical={false} />
              <XAxis dataKey="window_date" tickLine={false} axisLine={false} tick={{ fill: "#8290a5", fontSize: 10 }} />
              <YAxis domain={[0, 100]} tickLine={false} axisLine={false} tick={{ fill: "#8290a5", fontSize: 11 }} />
              <Tooltip />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="risk_score" name="Risk" fill="#527cf1" radius={[4, 4, 0, 0]} />
              <Bar dataKey="threshold_value" name="Threshold" fill="#e9b34d" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        ) : <div className="chart-empty">Run detection to view risk scores.</div>}
      </div>
    </Card>
  );
}
