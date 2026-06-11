FROM python:3.12-slim

# pdflatex for per-job tailored resume/cover-letter PDFs (cmap = ATS-clean text layer);
# latexdiff (own package on trixie, NOT in texlive-extra-utils) renders the highlighted
# baseline-vs-tailored diff PDF; texlive-plain-generic ships ulem.sty for its UNDERLINE markup
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base texlive-latex-recommended texlive-latex-extra \
    texlive-fonts-recommended latexdiff texlive-plain-generic && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY profile.yaml ./

# ENTRYPOINT (not CMD) so per-execution arg overrides (--tailor-job, --outreach-job)
# append to the command instead of replacing it.
ENTRYPOINT ["python", "-m", "jobpilot"]
