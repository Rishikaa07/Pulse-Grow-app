/** Loading states mirror the shape of what is coming, so nothing jumps. */
export function OverviewSkeleton() {
  return (
    <div className="mx-auto w-full max-w-[1080px] px-5 md:px-10" aria-busy="true" aria-label="Loading your watchlist">
      <div className="pt-10 md:pt-14">
        <div className="skeleton h-4 w-48 rounded" />
        <div className="skeleton mt-4 h-9 w-72 rounded" />
        <div className="skeleton mt-4 h-6 w-96 max-w-full rounded" />
      </div>
      <div className="skeleton mt-9 h-1.5 w-full rounded-full" />
      <div className="mt-5 flex gap-10">
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className="skeleton h-7 w-32 rounded" />
        ))}
      </div>
      <div className="mt-14 space-y-6">
        {[0, 1, 2].map((index) => (
          <div key={index} className="skeleton h-24 w-full rounded" />
        ))}
      </div>
    </div>
  );
}
