import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { VendorHistorySeries } from "../types/history";

type PriceTrendChartProps = {
  history: VendorHistorySeries[];
};

const chartColors = ["#111111", "#525252", "#a3a3a3", "#d4d4d4"];

function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(value);
}

export function PriceTrendChart({ history }: PriceTrendChartProps) {
  const rows: Array<Record<string, number | string>> = [];
  const lookup = new Map<string, Record<string, number | string>>();

  history.forEach((series) => {
    series.points.forEach((point) => {
      const date = point.timestamp.slice(0, 10);
      const row = lookup.get(date) ?? { date };
      row[series.vendor] = point.price;
      lookup.set(date, row);
    });
  });

  lookup.forEach((row) => rows.push(row));
  rows.sort((left, right) => String(left.date).localeCompare(String(right.date)));

  return (
    <div className="chart-shell">
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={rows}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e5e5e5" />
          <XAxis dataKey="date" stroke="#737373" />
          <YAxis
            stroke="#737373"
            tickFormatter={(value) =>
              new Intl.NumberFormat("en-IN", {
                maximumFractionDigits: 0,
              }).format(value as number)
            }
          />
          <Tooltip formatter={(value) => formatCurrency(Number(value))} />
          <Legend />
          {history.map((series, index) => (
            <Line
              key={series.vendor_product_id}
              type="monotone"
              dataKey={series.vendor}
              stroke={chartColors[index % chartColors.length]}
              strokeWidth={3}
              dot={{ r: 3 }}
              activeDot={{ r: 5 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
