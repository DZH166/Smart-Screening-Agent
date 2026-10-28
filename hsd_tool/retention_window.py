"""How long finished cloud tasks stay downloadable.

One value for both the numbering jobs (signed retention manifests) and the
material pipeline, because both share the same 12 GiB data volume and the same
promise to employees. Kept dependency-free so either side can import it.
"""

# 50 hours: shorter than the original three days, which kept roughly a week of
# dense collage output (2-3.5 GB/day) against an 11.7 GiB volume.
RETENTION_SECONDS = 50 * 60 * 60
