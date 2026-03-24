'use client';

interface PackageData {
  package_id?: string;
  title?: string;
  name?: string;
  status?: string;
  requirement_type?: string;
  estimated_value?: number | string;
  acquisition_method?: string;
  message?: string;
}

const STATUS_COLORS: Record<string, string> = {
  intake: 'bg-blue-100 text-blue-700',
  drafting: 'bg-yellow-100 text-yellow-800',
  review: 'bg-orange-100 text-orange-700',
  approved: 'bg-green-100 text-green-700',
  cancelled: 'bg-red-100 text-red-700',
};

export default function PackageStatusPanel({ text }: { text: string }) {
  let data: PackageData = {};
  try {
    const parsed = JSON.parse(text);
    data = typeof parsed === 'object' && parsed !== null ? parsed : {};
  } catch {
    return (
      <div className="border-t border-[#E5E9F0] px-3 py-2 bg-white max-h-64 overflow-y-auto">
        <pre className="text-gray-700 font-mono text-[11px] whitespace-pre-wrap break-all">{text}</pre>
      </div>
    );
  }

  const status = (data.status || 'unknown').toLowerCase();
  const statusColor = STATUS_COLORS[status] || 'bg-gray-100 text-gray-600';
  const title = data.title || data.name || 'Acquisition Package';
  const value = data.estimated_value
    ? typeof data.estimated_value === 'number'
      ? `$${data.estimated_value.toLocaleString()}`
      : data.estimated_value
    : null;

  return (
    <div className="border-t border-[#E5E9F0] bg-white px-3 py-2.5">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[9px] font-bold uppercase text-blue-600 tracking-wider">Package Update</span>
        <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${statusColor}`}>
          {status}
        </span>
      </div>

      <p className="text-xs font-medium text-gray-900 truncate">{title}</p>
      {data.package_id && (
        <p className="text-[10px] text-gray-400 font-mono">{data.package_id}</p>
      )}

      {/* Key fields row */}
      <div className="flex items-center gap-3 mt-1.5 text-[10px] text-gray-500">
        {data.requirement_type && (
          <span>{data.requirement_type.replace(/_/g, ' ')}</span>
        )}
        {value && <span>{value}</span>}
        {data.acquisition_method && (
          <span className="uppercase">{data.acquisition_method}</span>
        )}
      </div>

      {data.message && (
        <p className="text-[10px] text-gray-600 mt-1">{data.message}</p>
      )}
    </div>
  );
}
