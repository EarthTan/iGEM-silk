"""
Stages3 DuckDB 数据库接口模块。

提供统一的数据库读写接口，pipeline 脚本不直接构造 SQL。

设计原则:
- 所有表通过本模块创建和管理
- 写入使用批量 INSERT，不逐条插入
- 查询返回 Python 原生类型（list[dict]），不依赖 DataFrame
- 检查点操作单独封装，支持断点续跑
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

# ────────────────────────────────────────────────────────────────
# 路径与连接
# ────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "output3" / "pipeline.db"


class PipelineDB:
    """Pipeline DuckDB 连接封装。"""

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self.db_path = str(db_path)
        self._conn: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> duckdb.DuckDBPyConnection:
        """打开（或创建）数据库连接。"""
        if self._conn is None:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(self.db_path)
            self._conn.execute("SET memory_limit = '32GB'")
        return self._conn

    def close(self) -> None:
        """关闭数据库连接。"""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> PipelineDB:
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    # ────────────────────────────────────────────────────────────────
    # 初始化
    # ────────────────────────────────────────────────────────────────

    def init_schema(self) -> None:
        """创建所有表（幂等，IF NOT EXISTS）。"""
        conn = self.connect()

        # Stage 0: 候选肽段池
        conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_candidate_id START 1
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                candidate_id   BIGINT  DEFAULT nextval('seq_candidate_id'),
                source         VARCHAR NOT NULL,
                source_id      VARCHAR,
                header         VARCHAR,
                sequence       VARCHAR NOT NULL,
                length         SMALLINT NOT NULL,
                is_standard_aa BOOLEAN DEFAULT TRUE,
                cluster_id     VARCHAR,
                cluster_rep    BOOLEAN,
                PRIMARY KEY (candidate_id)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_candidates_source_id
            ON candidates(source, source_id)
        """)

        # Stage 1: 轻量初筛分数
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stage1_scores (
                candidate_id        BIGINT PRIMARY KEY REFERENCES candidates(candidate_id),
                anoxpepred_score    FLOAT,
                anoxpepred_success  BOOLEAN,
                algpred2_score      FLOAT,
                algpred2_success    BOOLEAN,
                scored_at           TIMESTAMP DEFAULT now()
            )
        """)

        # Stage 1: 通过者
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stage1_passed (
                candidate_id   BIGINT PRIMARY KEY REFERENCES candidates(candidate_id),
                anoxpepred_score FLOAT,
                passed_reason  VARCHAR
            )
        """)

        # Stage 2: 全量评分结果
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stage2_scores (
                candidate_id        BIGINT PRIMARY KEY REFERENCES candidates(candidate_id),
                anoxpepred_score    FLOAT,
                anoxpepred_success  BOOLEAN,
                bepipred3_score     FLOAT,
                bepipred3_success   BOOLEAN,
                plm4cpps_score      FLOAT,
                plm4cpps_success    BOOLEAN,
                graphcpp_score      FLOAT,
                graphcpp_success    BOOLEAN,
                temstapro_score     FLOAT,
                temstapro_success   BOOLEAN,
                sodope_score        FLOAT,
                sodope_success      BOOLEAN,
                mhcflurry_score     FLOAT,
                mhcflurry_success   BOOLEAN,
                toxinpred3_score    FLOAT,
                toxinpred3_success  BOOLEAN,
                hemopi2_score       FLOAT,
                hemopi2_success     BOOLEAN,
                scored_at           TIMESTAMP DEFAULT now()
            )
        """)

        # Stage 2: 排名
        conn.execute("""
            CREATE TABLE IF NOT EXISTS stage2_ranking (
                candidate_id    BIGINT PRIMARY KEY REFERENCES candidates(candidate_id),
                composite_score FLOAT NOT NULL,
                rank            BIGINT NOT NULL,
                weight_snapshot VARCHAR,
                ranked_at       TIMESTAMP DEFAULT now()
            )
        """)

        # Stage 3: 构造枚举
        conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS seq_construct_id START 1
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS constructs (
                construct_id   BIGINT DEFAULT nextval('seq_construct_id'),
                candidate_id   BIGINT REFERENCES candidates(candidate_id),
                linker         VARCHAR NOT NULL,
                position       VARCHAR NOT NULL,
                scaffold_seq   VARCHAR NOT NULL,
                linker_seq     VARCHAR NOT NULL,
                peptide_seq    VARCHAR NOT NULL,
                full_sequence  VARCHAR NOT NULL,
                PRIMARY KEY (construct_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS construct_scores (
                construct_id     BIGINT PRIMARY KEY REFERENCES constructs(construct_id),
                sodope_score     FLOAT,
                sodope_success   BOOLEAN,
                temstapro_score  FLOAT,
                temstapro_success BOOLEAN,
                scored_at        TIMESTAMP DEFAULT now()
            )
        """)

        # Stage 4: 结构预测
        conn.execute("""
            CREATE TABLE IF NOT EXISTS structure_jobs (
                job_id          BIGINT,
                construct_id    BIGINT REFERENCES constructs(construct_id),
                service         VARCHAR NOT NULL,
                status          VARCHAR DEFAULT 'pending',
                started_at      TIMESTAMP,
                completed_at    TIMESTAMP,
                error_message   VARCHAR,
                PRIMARY KEY (job_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS structure_results (
                construct_id    BIGINT PRIMARY KEY REFERENCES constructs(construct_id),
                service         VARCHAR NOT NULL,
                pdb_path        VARCHAR,
                confidence      FLOAT,
                plddt           FLOAT,
                completed_at    TIMESTAMP DEFAULT now()
            )
        """)

        # Stage 5: PDB 评估
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pdb_eval (
                construct_id     BIGINT PRIMARY KEY REFERENCES constructs(construct_id),
                sasa_score       FLOAT,
                sasa_success     BOOLEAN,
                aggrescan3d_score FLOAT,
                aggrescan3d_success BOOLEAN,
                scored_at        TIMESTAMP DEFAULT now()
            )
        """)

        # Stage 6: 最终排名
        conn.execute("""
            CREATE TABLE IF NOT EXISTS final_ranking (
                candidate_id    BIGINT REFERENCES candidates(candidate_id),
                construct_id    BIGINT REFERENCES constructs(construct_id),
                composite_score FLOAT NOT NULL,
                rank            BIGINT NOT NULL,
                weight_snapshot VARCHAR,
                ranked_at       TIMESTAMP DEFAULT now()
            )
        """)

        # 全局: 分数分布统计（方差感知权重的输入）
        conn.execute("""
            CREATE TABLE IF NOT EXISTS score_distribution (
                id                BIGINT,
                stage_name        VARCHAR NOT NULL,
                service_name      VARCHAR NOT NULL,
                count             BIGINT,
                mean              FLOAT,
                stddev            FLOAT,
                min               FLOAT,
                p01               FLOAT,
                p05               FLOAT,
                p25               FLOAT,
                p50               FLOAT,
                p75               FLOAT,
                p95               FLOAT,
                p99               FLOAT,
                max               FLOAT,
                winsorized_stddev FLOAT,
                computed_weight   FLOAT,
                computed_at       TIMESTAMP DEFAULT now()
            )
        """)

        # 全局: 权重配置记录
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weight_config (
                id                BIGINT,
                stage_name        VARCHAR NOT NULL,
                total_candidates  BIGINT,
                weight_formula    VARCHAR,
                weights           JSON,
                distribution_snapshot JSON,
                created_at        TIMESTAMP DEFAULT now()
            )
        """)

        # 全局: 检查点
        conn.execute("""
            CREATE TABLE IF NOT EXISTS checkpoint (
                stage           VARCHAR NOT NULL,
                step            VARCHAR,
                status          VARCHAR NOT NULL,
                total_items     BIGINT,
                processed_items BIGINT,
                error_message   VARCHAR,
                started_at      TIMESTAMP,
                completed_at    TIMESTAMP,
                updated_at      TIMESTAMP DEFAULT now(),
                PRIMARY KEY (stage, step)
            )
        """)

    # ────────────────────────────────────────────────────────────────
    # 批量化写入
    # ────────────────────────────────────────────────────────────────

    def insert_candidates(self, records: list[dict]) -> int:
        """
        批量插入候选肽。

        使用单条 INSERT + 多行 VALUES（较 executemany 快约 160 倍）。
        candidate_id 由 DEFAULT nextval 自动生成。
        """
        if not records:
            return 0
        conn = self.connect()
        BATCH = 10_000
        written = 0
        for start_idx in range(0, len(records), BATCH):
            batch = records[start_idx:start_idx + BATCH]
            # AA 序列只含 [ACDEFGHIKLMNPQRSTVWY]，无双引号/SQL 注入风险
            # header 中可能含单引号，用两个单引号转义
            _q = lambda s: str(s).replace("'", "''") if s else ""
            values = ",".join(
                f"('{r['source']}','{_q(r['source_id'])}','{_q(r.get('header'))}',"
                f"'{r['sequence']}',{r['length']},"
                f"{'true' if r.get('is_standard_aa', True) else 'false'})"
                for r in batch
            )
            conn.execute(
                f"INSERT INTO candidates (source, source_id, header, sequence, length, is_standard_aa) "
                f"VALUES {values}"
            )
            written += len(batch)
        return written

    def insert_stage1_scores(self, records: list[dict]) -> int:
        """
        批量写入 Stage 1 评分结果。

        使用 VALUES 子句批处理替代 executemany（实测快 100 倍）。
        candidate_id 是整数，无需引用。FLOAT 字段用 NULL 表示缺失。
        """
        if not records:
            return 0
        conn = self.connect()
        BATCH = 10_000
        written = 0

        def _null(v):
            return 'NULL' if v is None else str(v)

        def _bool(v):
            return 'true' if v else 'false'

        for start_idx in range(0, len(records), BATCH):
            batch = records[start_idx:start_idx + BATCH]
            values = ",".join(
                f"({r['candidate_id']},"
                f"{_null(r.get('anoxpepred_score'))},"
                f"{_bool(r.get('anoxpepred_success', False))},"
                f"{_null(r.get('algpred2_score'))},"
                f"{_bool(r.get('algpred2_success', False))})"
                for r in batch
            )
            conn.execute(f"""
                INSERT INTO stage1_scores
                    (candidate_id, anoxpepred_score, anoxpepred_success,
                     algpred2_score, algpred2_success)
                VALUES {values}
                ON CONFLICT (candidate_id) DO UPDATE SET
                    anoxpepred_score   = EXCLUDED.anoxpepred_score,
                    anoxpepred_success = EXCLUDED.anoxpepred_success,
                    algpred2_score     = EXCLUDED.algpred2_score,
                    algpred2_success   = EXCLUDED.algpred2_success
            """)
            written += len(batch)
        return written

    def mark_stage1_passed(self, records: list[dict]) -> int:
        """记录 Stage 1 通过者。"""
        conn = self.connect()
        conn.executemany("""
            INSERT INTO stage1_passed (candidate_id, anoxpepred_score, passed_reason)
            VALUES (?, ?, ?)
            ON CONFLICT (candidate_id) DO NOTHING
        """, [
            (r["candidate_id"], r.get("anoxpepred_score"), r.get("passed_reason", "passed"))
            for r in records
        ])
        return len(records)

    # ────────────────────────────────────────────────────────────────
    # 聚合查询
    # ────────────────────────────────────────────────────────────────

    def compute_distribution(self, table: str, score_column: str) -> dict:
        """计算某个分数列的分布统计。"""
        conn = self.connect()
        row = conn.execute(f"""
            SELECT
                COUNT(*)                                             AS count,
                AVG({score_column})                                  AS mean,
                STDDEV({score_column})                               AS stddev,
                MIN({score_column})                                  AS min,
                PERCENTILE_CONT(0.01)  WITHIN GROUP (ORDER BY {score_column}) AS p01,
                PERCENTILE_CONT(0.05)  WITHIN GROUP (ORDER BY {score_column}) AS p05,
                PERCENTILE_CONT(0.25)  WITHIN GROUP (ORDER BY {score_column}) AS p25,
                PERCENTILE_CONT(0.50)  WITHIN GROUP (ORDER BY {score_column}) AS p50,
                PERCENTILE_CONT(0.75)  WITHIN GROUP (ORDER BY {score_column}) AS p75,
                PERCENTILE_CONT(0.95)  WITHIN GROUP (ORDER BY {score_column}) AS p95,
                PERCENTILE_CONT(0.99)  WITHIN GROUP (ORDER BY {score_column}) AS p99,
                MAX({score_column})                                  AS max
            FROM {table}
            WHERE {score_column} IS NOT NULL
        """).fetchone()
        if row is None or row[0] == 0:
            return {}
        columns = ["count", "mean", "stddev", "min", "p01", "p05", "p25",
                    "p50", "p75", "p95", "p99", "max"]
        return dict(zip(columns, [float(v) if v is not None else None for v in row]))

    # ────────────────────────────────────────────────────────────────
    # 检查点
    # ────────────────────────────────────────────────────────────────

    def set_checkpoint(self, stage: str, step: str, status: str,
                       total: int = 0, processed: int = 0,
                       error: str | None = None) -> None:
        """更新检查点状态。"""
        conn = self.connect()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO checkpoint (stage, step, status, total_items, processed_items,
                                    error_message, updated_at, started_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (stage, step) DO UPDATE SET
                status          = EXCLUDED.status,
                total_items     = EXCLUDED.total_items,
                processed_items = EXCLUDED.processed_items,
                error_message   = COALESCE(EXCLUDED.error_message, checkpoint.error_message),
                updated_at      = EXCLUDED.updated_at
        """, [stage, step, status, total, processed, error, now, now])

    def get_checkpoint(self, stage: str) -> dict | None:
        """查询某个阶段的最新检查点状态。"""
        conn = self.connect()
        row = conn.execute("""
            SELECT stage, step, status, total_items, processed_items, error_message
            FROM checkpoint
            WHERE stage = ?
            ORDER BY updated_at DESC
            LIMIT 1
        """, [stage]).fetchone()
        if row is None:
            return None
        cols = ["stage", "step", "status", "total_items", "processed_items", "error_message"]
        return dict(zip(cols, row))

    def get_last_processed_id(self, table: str, id_column: str = "candidate_id") -> int:
        """查询某个表已处理的最大 ID，用于断点续跑。"""
        conn = self.connect()
        row = conn.execute(f"SELECT COALESCE(MAX({id_column}), 0) FROM {table}").fetchone()
        return int(row[0]) if row else 0

    # ────────────────────────────────────────────────────────────────
    # 工具
    # ────────────────────────────────────────────────────────────────

    def table_exists(self, table: str) -> bool:
        """检查表是否存在。"""
        conn = self.connect()
        row = conn.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_name = ?
        """, [table]).fetchone()
        return row is not None

    def row_count(self, table: str) -> int:
        """返回表的总行数。"""
        conn = self.connect()
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        return int(row[0]) if row else 0
