"""One fetcher per source (spec §5). Each caches raw responses under data/raw/<source>/
and writes processed tables that `src.snapshot` publishes to data/snapshot/."""
