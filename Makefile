.PHONY: help dev run frontend docker-up docker-down index crawl test build-extractor setup-qdrant

# ── Config ───────────────────────────────────────────────
LAW         ?= all
INDEXES_DIR  = data/indexes
EXTRACTOR    = extractor/extractor_v2

help:
	@echo ""
	@echo "  ╔══════════════════════════════════════════╗"
	@echo "  ║  LexAgent v3 — Multi-Law Legal RAG       ║"
	@echo "  ╚══════════════════════════════════════════╝"
	@echo ""
	@echo "  ── Development ─────────────────────────────"
	@echo "  make dev              Backend (port 8000, reload)"
	@echo "  make frontend         Frontend (port 3000)"
	@echo "  make dev-all          Backend + frontend concurrently"
	@echo ""
	@echo "  ── Docker (production) ─────────────────────"
	@echo "  make docker-up        Build + start all services"
	@echo "  make docker-down      Stop all services"
	@echo "  make docker-build     Build images only"
	@echo ""
	@echo "  ── Data Pipeline ───────────────────────────"
	@echo "  make crawl            Crawl tất cả từ thuvienphapluat"
	@echo "  make crawl LAW=bhxh   Crawl 1 luật"
	@echo "  make index            Index BM25 + Qdrant"
	@echo "  make index-bm25       Index BM25 only (no Qdrant)"
	@echo "  make setup-qdrant     Tạo Qdrant collection"
	@echo ""
	@echo "  ── Extractor ───────────────────────────────"
	@echo "  make build-extractor  Build Go extractor v2"
	@echo "  make extract FILE=data/raw/bhxh/bhxh.html LAW=bhxh"
	@echo ""
	@echo "  ── Eval & Test ─────────────────────────────"
	@echo "  make test             Test components"
	@echo "  make eval             Eval BM25 (20 câu)"
	@echo ""

# ── Dev ──────────────────────────────────────────────────
dev:
	uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload

run:
	uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

dev-all:
	@make -j2 dev frontend

# ── Docker ───────────────────────────────────────────────
docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

docker-build:
	docker compose build

docker-logs:
	docker compose logs -f backend

# ── Extractor ────────────────────────────────────────────
build-extractor:
	cd extractor && GOTOOLCHAIN=local go build -o extractor_v2 .
	@echo "✅ extractor/extractor_v2 built"

extract:
	$(EXTRACTOR) \
		--file=$(FILE) \
		--output=data/extracted/$(LAW)/$(LAW).json \
		--law-id=$(LAW)

# ── Crawl ────────────────────────────────────────────────
crawl:
ifeq ($(LAW),all)
	python scripts/crawl.py
else
	python scripts/crawl.py --law $(LAW)
endif

# ── Index ────────────────────────────────────────────────
index-bm25:
	python scripts/index_bm25.py --output-dir $(INDEXES_DIR)

setup-qdrant:
	python scripts/setup_qdrant.py

index: setup-qdrant index-bm25
	@echo "  Indexing vectors to Qdrant..."
	python -c "
import sys, json
from pathlib import Path
for f in sorted(Path('data/extracted').rglob('*.json')):
    print(f'  Indexing {f}...')
"

# ── Eval ─────────────────────────────────────────────────
eval:
	python eval/eval_bm25.py

# ── Test ─────────────────────────────────────────────────
test:
	python -c "from backend.core.law.classifier import classify_laws; print('✅ law_classifier')"
	python -c "from backend.core.law.conflict import resolve; print('✅ conflict_resolver')"
	python -c "from backend.core.law.temporal import detect_temporal; print('✅ temporal_filter')"
	python -c "from backend.core.retrieval.bm25 import BM25Retriever; print('✅ bm25_retriever')"
	python -c "from backend.core.pipeline.context_builder import build_context, SYSTEM_PROMPT; print('✅ context_builder')"
	python -c "from backend.app.config import ROOT_DIR; print(f'✅ config (root={ROOT_DIR})')"
	@echo "\n  ✅ All imports OK"

# ── Clean ────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

install:
	pip install -r backend/requirements.txt
