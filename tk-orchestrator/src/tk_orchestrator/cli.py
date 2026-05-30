from __future__ import annotations

import asyncio
import re
import shutil
import sys
from pathlib import Path

import click

from .config import Config, load_config
from .models import Channel, Job, Video, get_session, init_db
from .logging_config import setup_logging


# ── helpers ───────────────────────────────────────────────────────────────────


def _bootstrap(config_path: str | None) -> Config:
    config = load_config(Path(config_path) if config_path else None)
    init_db(config)
    setup_logging()
    return config


def _extract_username(url: str) -> str:
    """Extract username from a TikTok channel URL or @handle."""
    m = re.search(r"tiktok\.com/@([^/?#]+)", url)
    if m:
        return m.group(1)
    return url.lstrip("@")


def _normalize_channel_input(value: str) -> tuple[str, str]:
    username = _extract_username(value.strip())
    return username, f"https://www.tiktok.com/@{username}"


def _parse_tiktok_video_url(url: str) -> tuple[str, str]:
    """Return (username, video_id) from a TikTok video URL."""
    m = re.match(r"https?://(?:www\.)?tiktok\.com/@([^/]+)/video/(\d+)", url)
    if not m:
        raise click.UsageError(f"Not a valid TikTok video URL: {url}")
    return m.group(1), m.group(2)


def _ensure_channel(username: str) -> int:
    _, channel_url = _normalize_channel_input(username)
    with get_session() as s:
        ch = s.query(Channel).filter(Channel.username == username).first()
        if ch:
            return ch.id  # type: ignore[return-value]
        ch = Channel(username=username, url=channel_url)
        s.add(ch)
        s.flush()
        return ch.id  # type: ignore[return-value]


def _seed_default_channels(config: Config) -> int:
    added = 0
    if not config.default_channels:
        return added

    with get_session() as s:
        existing_usernames = {channel.username for channel in s.query(Channel).all()}
        for value in config.default_channels:
            username, channel_url = _normalize_channel_input(value)
            if username in existing_usernames:
                continue
            s.add(Channel(username=username, url=channel_url))
            existing_usernames.add(username)
            added += 1

    return added


def _ensure_job(video_id: str, channel_id: int, url: str) -> int:
    with get_session() as s:
        video = s.get(Video, video_id)
        if not video:
            video = Video(id=video_id, channel_id=channel_id, url=url)
            s.add(video)
        existing = (
            s.query(Job)
            .filter(
                Job.video_id == video_id,
                Job.status.in_(["pending", "running", "interrupted"]),
            )
            .first()
        )
        if existing:
            return existing.id  # type: ignore[return-value]
        job = Job(video_id=video_id, status="pending")
        s.add(job)
        s.flush()
        return job.id  # type: ignore[return-value]


# ── CLI root ──────────────────────────────────────────────────────────────────


@click.group()
@click.option("--config", "config_path", default=None, help="Path to config.yaml")
@click.pass_context
def main(ctx: click.Context, config_path: str | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


# ── channel commands ──────────────────────────────────────────────────────────


@main.group()
def channel() -> None:
    """Manage monitored TikTok channels."""


@channel.command("add")
@click.argument("url")
@click.pass_context
def channel_add(ctx: click.Context, url: str) -> None:
    """Add a channel to monitor."""
    config = _bootstrap(ctx.obj.get("config_path"))
    username, channel_url = _normalize_channel_input(url)
    with get_session() as s:
        if s.query(Channel).filter(Channel.username == username).first():
            click.echo(f"Channel @{username} is already being monitored.")
            return
        s.add(Channel(username=username, url=channel_url))
    click.echo(f"Added @{username}")


@channel.command("list")
@click.pass_context
def channel_list(ctx: click.Context) -> None:
    """List all monitored channels."""
    _bootstrap(ctx.obj.get("config_path"))
    with get_session() as s:
        channels = s.query(Channel).order_by(Channel.added_at.desc()).all()
        if not channels:
            click.echo("No channels.")
            return
        for ch in channels:
            status = "active" if ch.is_active else "inactive"
            last = (
                ch.last_checked_at.strftime("%Y-%m-%d %H:%M")
                if ch.last_checked_at
                else "never"
            )
            click.echo(f"  @{ch.username:<30} [{status}]  last checked: {last}")


@channel.command("remove")
@click.argument("username")
@click.pass_context
def channel_remove(ctx: click.Context, username: str) -> None:
    """Stop monitoring a channel."""
    _bootstrap(ctx.obj.get("config_path"))
    username = username.lstrip("@")
    with get_session() as s:
        ch = s.query(Channel).filter(Channel.username == username).first()
        if not ch:
            click.echo(f"Channel @{username} not found.")
            sys.exit(1)
        ch.is_active = False
    click.echo(f"Deactivated @{username}")


@channel.command("check")
@click.argument("username")
@click.pass_context
def channel_check(ctx: click.Context, username: str) -> None:
    """Manually poll a channel and run the pipeline for any new videos."""
    config = _bootstrap(ctx.obj.get("config_path"))
    username = username.lstrip("@")
    asyncio.run(_channel_check_async(username, config))


async def _channel_check_async(username: str, config: Config) -> None:
    from .worker import claim_job, run_pipeline
    from .scheduler import poll_channel

    with get_session() as s:
        ch = s.query(Channel).filter(Channel.username == username).first()
        if not ch:
            click.echo(
                f"Channel @{username} not found. Add it first with: tk-orch channel add <url>"
            )
            return
        channel_id, channel_url = ch.id, ch.url

    result = await poll_channel(channel_id, username, channel_url, config)
    if not result.job_ids:
        if result.reason == "channel_limit_reached":
            click.echo(
                f"Skipped @{username}: channel stored video limit reached "
                f"({result.channel_video_total}/{config.max_videos_per_channel})."
            )
            return
        if result.reason == "total_limit_reached":
            click.echo(
                "Skipped poll: global stored video limit reached "
                f"({result.total_video_total}/{config.max_videos_total})."
            )
            return
        click.echo("No new videos found.")
        return

    click.echo(f"Found {len(result.job_ids)} new video(s). Running pipeline...")
    for job_id in result.job_ids:
        prior_status = claim_job(job_id)
        if prior_status is None:
            click.echo(f"Skipped job {job_id}: already running elsewhere.")
            continue
        await run_pipeline(job_id, config, prior_status=prior_status)


# ── run commands ──────────────────────────────────────────────────────────────


@main.command("run")
@click.argument("target")
@click.pass_context
def run(ctx: click.Context, target: str) -> None:
    """Run pipeline for a video URL, or 'all' to process all pending videos."""
    config = _bootstrap(ctx.obj.get("config_path"))
    if target.lower() == "all":
        asyncio.run(_run_all_async(config))
    else:
        asyncio.run(_run_video_async(target, config))


async def _run_all_async(config: Config) -> None:
    from .worker import claim_job, run_pipeline

    with get_session() as s:
        queued = s.query(Job).filter(Job.status.in_(["pending", "interrupted"])).all()
        job_ids = [j.id for j in queued]

    if not job_ids:
        click.echo("No pending or interrupted jobs.")
        return

    click.echo(f"Running {len(job_ids)} pending/interrupted job(s)...")
    for job_id in job_ids:
        prior_status = claim_job(job_id)
        if prior_status is None:
            click.echo(f"Skipped job {job_id}: already running elsewhere.")
            continue
        await run_pipeline(job_id, config, prior_status=prior_status)


async def _run_video_async(url: str, config: Config) -> None:
    from .worker import claim_job, run_pipeline

    username, video_id = _parse_tiktok_video_url(url)
    channel_id = _ensure_channel(username)
    job_id = _ensure_job(video_id, channel_id, url)
    prior_status = claim_job(job_id)
    if prior_status is None:
        click.echo(f"Job {job_id} is already running elsewhere.")
        return
    await run_pipeline(job_id, config, prior_status=prior_status)


# ── reset ─────────────────────────────────────────────────────────────────────


@main.command("reset")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def reset(ctx: click.Context, yes: bool) -> None:
    """Delete orchestrator database and generated output."""
    config = _bootstrap(ctx.obj.get("config_path"))
    db_path = config.db_path
    output_dir = config.output_dir

    click.echo("This will permanently delete:")
    click.echo(f"  DB:     {db_path}")
    click.echo(f"  Output: {output_dir}")
    if not yes and not click.confirm("Continue?", default=False):
        click.echo("Aborted.")
        return

    if db_path.exists():
        db_path.unlink()
        click.echo(f"Deleted DB: {db_path}")
    else:
        click.echo(f"DB not found: {db_path}")

    if output_dir.exists():
        shutil.rmtree(output_dir)
        click.echo(f"Deleted output: {output_dir}")
    else:
        click.echo(f"Output not found: {output_dir}")


# ── job inspection ────────────────────────────────────────────────────────────


@main.command("jobs")
@click.pass_context
def jobs_list(ctx: click.Context) -> None:
    """List the 20 most recent jobs."""
    _bootstrap(ctx.obj.get("config_path"))
    with get_session() as s:
        job_list = s.query(Job).order_by(Job.created_at.desc()).limit(20).all()
        if not job_list:
            click.echo("No jobs.")
            return
        for j in job_list:
            step = f"  step={j.current_step}" if j.current_step else ""
            failed = f"  failed_at={j.failed_step}" if j.failed_step else ""
            click.echo(f"  [{j.id:>4}] {j.status:<12} video={j.video_id}{step}{failed}")


@main.command("job")
@click.argument("job_id", type=int)
@click.pass_context
def job_detail(ctx: click.Context, job_id: int) -> None:
    """Show detailed status of a specific job."""
    _bootstrap(ctx.obj.get("config_path"))
    with get_session() as s:
        j = s.get(Job, job_id)
        if not j:
            click.echo(f"Job {job_id} not found.")
            sys.exit(1)
        click.echo(f"Job {j.id}")
        click.echo(f"  video_id:     {j.video_id}")
        click.echo(f"  status:       {j.status}")
        click.echo(f"  current_step: {j.current_step or '-'}")
        click.echo(f"  failed_step:  {j.failed_step or '-'}")
        click.echo(f"  video_path:   {j.video_path or '-'}")
        click.echo(f"  srt_path:     {j.srt_path or '-'}")
        click.echo(f"  vtt_path:     {j.vtt_path or '-'}")
        click.echo(f"  created_at:   {j.created_at}")
        click.echo(f"  started_at:   {j.started_at or '-'}")
        click.echo(f"  completed_at: {j.completed_at or '-'}")
        if j.error_message:
            click.echo(f"  error:\n{j.error_message}")


# ── start ─────────────────────────────────────────────────────────────────────


@main.command("start")
@click.option("--host", default="0.0.0.0", show_default=True, help="API server host")
@click.option("--port", default=19099, show_default=True, help="API server port")
@click.option(
    "--refresh/--no-refresh",
    default=None,
    help="Enable or disable channel polling, retention, and background processing.",
)
@click.pass_context
def start(
    ctx: click.Context,
    host: str,
    port: int,
    refresh: bool | None,
) -> None:
    """Start the scheduler, queue worker, and API server."""
    config = _bootstrap(ctx.obj.get("config_path"))
    if refresh is not None:
        config.refresh_enabled = refresh
    asyncio.run(_start_async(config, host, port))


async def _start_async(config: Config, host: str, port: int) -> None:
    import uvicorn

    from .api import app, configure
    from .worker import recover_interrupted_jobs, worker
    from .scheduler import setup_scheduler

    configure(config)
    seeded_channels = _seed_default_channels(config)
    recovered_jobs = recover_interrupted_jobs()

    uv_config = uvicorn.Config(
        app, host=host, port=port, loop="none", log_level="warning"
    )
    server = uvicorn.Server(uv_config)

    click.echo(f"tk-orchestrator started  (API: http://{host}:{port})")
    click.echo(
        "Refresh mode: on"
        if config.refresh_enabled
        else "Refresh mode: off (no polling, retention, or background processing)"
    )
    if seeded_channels:
        click.echo(f"Seeded {seeded_channels} default channel(s).")
    if recovered_jobs:
        click.echo(f"Recovered {len(recovered_jobs)} interrupted job(s).")
    if not config.refresh_enabled:
        await server.serve()
        return

    scheduler = setup_scheduler(config)
    scheduler.start()
    await asyncio.gather(worker(config), server.serve())
