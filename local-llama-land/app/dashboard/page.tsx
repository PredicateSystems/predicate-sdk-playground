import { DashboardClient } from '../../components/client/dashboard';

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-semibold">Dashboard</h1>
        <p className="text-white/70">
          KPI cards + table + optional live DOM churn (use <code className="text-white">?live=1</code>).
        </p>
      </div>
      <DashboardClient />
    </div>
  );
}

