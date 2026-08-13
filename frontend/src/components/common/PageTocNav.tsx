type TocSection = {
  title: string;
  slug: string;
};

export function PageTocNav({ sections }: { sections: TocSection[] }) {
  return (
    <nav aria-label="Table of contents" className="hidden lg:block">
      <div className="sticky top-24 space-y-4">
        <p className="flex items-center gap-2 text-xs font-semibold tracking-[0.15em] text-foreground">
          <span className="h-3 w-0.5 rounded-full bg-destructive" aria-hidden="true" />
          ON THIS PAGE
        </p>
        <ul className="space-y-1 border-l border-border text-sm">
          {sections.map((section) => (
            <li key={section.slug}>
              <a
                href={`#${section.slug}`}
                className="block border-l -ml-px border-transparent py-1.5 pl-4 text-muted-foreground transition-colors hover:border-destructive hover:text-foreground"
              >
                {section.title}
              </a>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
