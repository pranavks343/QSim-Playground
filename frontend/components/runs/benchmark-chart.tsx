"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

export type BenchmarkChartDatum = {
  bitstring: string;
  shots: number;
  objective: number;
};

type Props = {
  data: BenchmarkChartDatum[];
};

export default function BenchmarkChart({ data }: Props) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 16, bottom: 24, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" opacity={0.4} />
        <XAxis
          dataKey="bitstring"
          tick={{ fontSize: 11, fontFamily: "monospace" }}
          interval={0}
          angle={-15}
          dy={8}
        />
        <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
        <Tooltip
          cursor={{ fillOpacity: 0.1 }}
          formatter={(value) => [`${String(value)} shots`, "Count"]}
          labelFormatter={(label) => `Bitstring ${String(label)}`}
        />
        <Bar dataKey="shots" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
