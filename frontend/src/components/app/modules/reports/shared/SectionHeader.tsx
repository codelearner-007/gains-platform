import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';

interface SectionHeaderProps {
  title: string;
}

export default function SectionHeader({ title }: SectionHeaderProps) {
  return (
    <div
      className="px-3 py-1.5 text-[13px] font-bold text-black border"
      style={{ backgroundColor: HEADER_BAR_BG, borderColor: LAYOUT_BORDER }}
    >
      {title}
    </div>
  );
}
