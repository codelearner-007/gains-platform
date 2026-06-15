/**
 * KPI tile value renderer for the Instructor(s) card, shared by QRA + SDD.
 * Stacks instructor names vertically; falls back to an em-dash when empty.
 */
export default function InstructorsValue({
  instructors,
}: {
  instructors: string[];
}) {
  const list = instructors.length > 0 ? instructors : ['—'];
  return (
    <div className="flex flex-col items-center justify-center gap-0.5 leading-tight">
      {list.map((name, i) => (
        <div
          key={i}
          className="text-[13px] font-bold text-black text-center leading-tight"
        >
          {name}
        </div>
      ))}
    </div>
  );
}
