"""Office work inside the isolated environment.

The agent does office work in a container rather than on the owner's desktop: a
document, a spreadsheet and a presentation are written as flat ODF sources,
converted by the office suite into `.odt`, `.xlsx`, `.pptx` and PDF inside the
container, and the results are copied out. No host directory is mounted, so the
environment cannot reach the owner's files, and the container is removed when
the job ends whether it succeeded or not.

Three decisions are load-bearing.

**The evidence is the container's own listing.** A file that exists on the host
is not proof that the environment produced it, so every job keeps the `ls`
output read inside the container and reports each artifact with its size and
digest taken after the copy, and each PDF's page count when it can be measured.

**Every step is a record.** Each conversion and the evidence read are published
as `Action` records in a stream of their own, so a demo cannot claim work the
graph does not hold. The stream is deliberately not the product's: demo records
must never mix into the owner's own stream.

**A missing prerequisite is named, never guessed.** No Docker, no image, a
conversion that failed — each is a refusal with a code and a reason, because the
alternative is a job that reports success for files nobody produced.
"""
from __future__ import annotations

import asyncio
import hashlib
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

from oneiro import config
from oneiro.graph_worker import GraphWorker
from oneiro.records import Action, Effect, EffectOutcome, Experience, Provenance, State, now

#: The image the isolated environment runs from. `vm/Dockerfile` builds it.
IMAGE = "oneiro-office:local"
#: Paths inside the container, always in POSIX form. `Path("/work") / "in"` would
#: render as `\work\in` on Windows, and the container would make a folder whose
#: name contains a backslash while every later path pointed at /work/in.
MOUNT = "/work"
IN_DIR = MOUNT + "/in"
OUT_DIR = MOUNT + "/out"
#: The stream demo records are published to. Never the product's own stream.
DEMO_STREAM = "demo"

#: A conversion and a container start are seconds; a first build downloads a whole
#: office suite from a package mirror and is measured in minutes, so it gets its own,
#: larger bound instead of failing a build that is still running.
CONVERT_TIMEOUT = 300.0
BUILD_TIMEOUT = 1800.0


class OfficeError(RuntimeError):
    """A refusal with a name, so nothing is reported as done that was not."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


# ---------------------------------------------------------------- the sources


def _flat_document(mimetype: str, body: str, styles: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<office:document '
        'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
        'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
        'xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
        'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
        'xmlns:presentation="urn:oasis:names:tc:opendocument:xmlns:presentation:1.0" '
        'xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0" '
        'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
        'office:version="1.3" office:mimetype="' + mimetype + '">'
        + styles + "<office:body>" + body + "</office:body></office:document>\n"
    )


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def document_source(topic: str) -> str:
    """A text document as flat ODF: a heading and two paragraphs about the topic."""
    body = (
        "<office:text>"
        f'<text:h text:outline-level="1">{_escape(topic)}</text:h>'
        f"<text:p>{_escape(topic)} — документ создан в изолированной среде Oneiro.</text:p>"
        "<text:p>Документ собран офисным пакетом внутри контейнера; файлы этого "
        "задания описаны в графе памяти записями действий.</text:p>"
        "</office:text>"
    )
    return _flat_document("application/vnd.oasis.opendocument.text", body)


def spreadsheet_source(topic: str) -> str:
    """A spreadsheet as flat ODF: a label column and a number column."""
    rows = [("Шаг", "Значение"), ("Документ", "1"), ("Таблица", "2"), ("Презентация", "3")]
    cells = []
    for label, value in rows:
        cells.append(
            "<table:table-row>"
            f'<table:table-cell office:value-type="string"><text:p>{_escape(label)}</text:p>'
            "</table:table-cell>"
            f'<table:table-cell office:value-type="string"><text:p>{_escape(value)}</text:p>'
            "</table:table-cell>"
            "</table:table-row>"
        )
    body = (
        "<office:spreadsheet>"
        f'<table:table table:name="{_escape(topic)[:24]}">'
        '<table:table-column table:style-name="LabelColumn"/>'
        '<table:table-column table:style-name="ValueColumn"/>'
        + "".join(cells) + "</table:table>"
        "</office:spreadsheet>"
    )
    styles = (
        '<office:automatic-styles>'
        '<style:style style:name="LabelColumn" style:family="table-column">'
        '<style:table-column-properties style:column-width="5cm"/></style:style>'
        '<style:style style:name="ValueColumn" style:family="table-column">'
        '<style:table-column-properties style:column-width="3cm"/></style:style>'
        '</office:automatic-styles>'
    )
    return _flat_document("application/vnd.oasis.opendocument.spreadsheet", body, styles)


def presentation_source(topic: str) -> str:
    """A presentation as flat ODF: a title slide and one content slide."""
    def frame(name: str, x: str, y: str, text: str) -> str:
        return (
            f'<draw:frame draw:name="{name}" svg:x="{x}" svg:y="{y}" '
            'svg:width="24cm" svg:height="3cm"><draw:text-box>'
            f"<text:p>{_escape(text)}</text:p></draw:text-box></draw:frame>"
        )

    body = (
        "<office:presentation>"
        '<draw:page draw:name="Slide1">'
        + frame("Title", "1cm", "8cm", topic)
        + "</draw:page>"
        '<draw:page draw:name="Slide2">'
        + frame("Title2", "1cm", "1cm", "Что сделано")
        + frame("Body", "1cm", "4cm", "Документ, таблица и презентация собраны в контейнере")
        + "</draw:page>"
        "</office:presentation>"
    )
    return _flat_document("application/vnd.oasis.opendocument.presentation", body)


#: Source file name -> builder. The suffixes are what the suite reads as flat ODF.
SOURCES: dict[str, Callable[[str], str]] = {
    "note.fodt": document_source,
    "table.fods": spreadsheet_source,
    "slides.fodp": presentation_source,
}

#: Source name -> (binary format, the extension the suite writes).
CONVERSIONS: dict[str, tuple[str, str]] = {
    "note.fodt": ("odt", ".odt"),
    "table.fods": ("xlsx", ".xlsx"),
    "slides.fodp": ("pptx", ".pptx"),
}


# ------------------------------------------------------------------- results


@dataclass(frozen=True)
class Artifact:
    """One file the environment produced, measured after it was copied out."""

    name: str
    path: Path
    bytes: int
    sha256: str
    pages: int | None = None
    pages_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "path": str(self.path), "bytes": self.bytes,
                "sha256": self.sha256, "pages": self.pages, "pages_reason": self.pages_reason}


@dataclass(frozen=True)
class Step:
    """One command run in the environment, with what it produced."""

    name: str
    command: tuple[str, ...]
    exit_code: int
    output: str
    record_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "command": list(self.command), "exit_code": self.exit_code,
                "output": self.output, "record_id": self.record_id}


@dataclass
class OfficeJob:
    """An office job: its sources, the environment's own evidence, its artifacts."""

    id: str
    topic: str
    image: str
    container: str
    workdir: Path
    sources: dict[str, Path]
    artifacts: list[Artifact] = field(default_factory=list)
    steps: list[Step] = field(default_factory=list)
    listing: str = ""
    listing_files: tuple[str, ...] = ()
    stopped: bool = False
    records: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "topic": self.topic, "image": self.image,
                "container": self.container, "workdir": str(self.workdir),
                "sources": {name: str(path) for name, path in self.sources.items()},
                "artifacts": [item.to_dict() for item in self.artifacts],
                "steps": [item.to_dict() for item in self.steps],
                "listing": self.listing, "listing_files": list(self.listing_files),
                "stopped": self.stopped, "records": list(self.records)}


# --------------------------------------------------------------- the sandbox

Runner = Callable[..., tuple[int, str, str]]


def _subprocess_runner(argv: list[str], *, timeout: float = CONVERT_TIMEOUT) -> tuple[int, str, str]:
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise OfficeError("docker_absent", "the docker command was not found on PATH") from None
    except subprocess.TimeoutExpired:
        raise OfficeError("timeout", f"the command did not answer within {timeout:.0f}s") from None
    return done.returncode, done.stdout, done.stderr


def pdf_pages(path: Path) -> tuple[int | None, str]:
    """How many pages a PDF has, or why it could not be measured."""
    try:
        import PyPDF2
    except ImportError:
        return None, "PyPDF2 is not installed, so the page count was not measured"
    try:
        with path.open("rb") as stream:
            reader = PyPDF2.PdfReader(stream)
            return len(reader.pages), ""
    except Exception as exc:
        return None, f"not readable as a PDF ({exc.__class__.__name__})"


def _docker_path(path: Path) -> str:
    """A host path in the form the Docker CLI parses.

    `C:\\dir\\file` carries a colon, and `docker cp` reads the first colon as the
    `source:destination` separator, so the drive letter is taken for a container
    name and the copy fails with "could not find the file". Forward slashes keep
    the path one argument on Windows and are unchanged on POSIX.
    """
    return Path(path).as_posix()


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


class Sandbox:
    """The isolated environment: an image, a container, and the office suite in it.

    `runner` is injectable so the orchestration can be tested without Docker; the
    real runs in this repository go through `_subprocess_runner`.
    """

    def __init__(self, *, runner: Runner | None = None, image: str = IMAGE,
                 docker: str = "docker", dockerfile: Path | None = None) -> None:
        self._runner = runner or _subprocess_runner
        self.image = image
        self.docker = docker
        self.dockerfile = dockerfile or (Path(__file__).resolve().parents[2] / "vm" / "Dockerfile")

    def _run(self, argv: list[str], *, timeout: float = CONVERT_TIMEOUT) -> tuple[int, str, str]:
        return self._runner([self.docker, *argv], timeout=timeout)

    def _must(self, argv: list[str], what: str, *, timeout: float = CONVERT_TIMEOUT) -> str:
        code, out, err = self._run(argv, timeout=timeout)
        if code != 0:
            raise OfficeError("command_failed",
                              f"{what} exited {code}: {(err or out).strip().splitlines()[-1:] or ['']}"[:400])
        return out

    def image_present(self) -> bool:
        try:
            code, out, _ = self._run(["image", "inspect", self.image, "--format", "{{.Id}}"],
                                     timeout=60.0)
        except OfficeError:
            return False
        return code == 0 and bool(out.strip())

    def build(self) -> str:
        """Build the image from `vm/Dockerfile`. Refuses if the file is missing."""
        if not self.dockerfile.is_file():
            raise OfficeError("dockerfile_absent", f"{self.dockerfile} does not exist")
        code, out, err = self._run(["build", "-t", self.image, "-f", _docker_path(self.dockerfile),
                                    _docker_path(self.dockerfile.parent)], timeout=BUILD_TIMEOUT)
        # The image is the evidence, not the builder's exit status: a build whose
        # client timed out while the daemon finished is a success, and reporting it
        # as a failure is how a working image gets built twice.
        if not self.image_present():
            detail = (err or out).strip()[-300:]
            raise OfficeError("build_failed", f"docker build exited {code}: {detail}")
        # The tag, not the builder's last line: callers name the image they will run.
        return self.image

    def ensure_image(self, *, build: bool = True) -> str:
        if self.image_present():
            return self.image
        if not build:
            raise OfficeError("image_absent",
                              f"the image {self.image} is not built; run: oneiro office image")
        return self.build()

    def run(self, topic: str, *, out_dir: Path | None = None,
            prefix: str = "oneiro-office") -> OfficeJob:
        """Do the office work once, in a container, and take the files out of it.

        The container never sees a host directory: sources go in with `docker cp`,
        results come out the same way, and the container is removed in a `finally`
        so a failed conversion cannot leave one behind.
        """
        if not shutil.which(self.docker) and self._runner is _subprocess_runner:
            raise OfficeError("docker_absent", "the docker command was not found on PATH")
        self.ensure_image()
        job_id = uuid.uuid4().hex[:12]
        container = f"{prefix}-{job_id}"
        workdir = Path(out_dir) if out_dir is not None else Path(tempfile.gettempdir()) / "oneiro-demo"
        workdir = workdir / job_id
        incoming, produced = workdir / "in", workdir / "out"
        incoming.mkdir(parents=True, exist_ok=True)
        produced.mkdir(parents=True, exist_ok=True)
        job = OfficeJob(id=job_id, topic=topic, image=self.image, container=container,
                        workdir=workdir, sources={})

        try:
            self._must(["run", "-d", "--name", container, "--network", "none",
                        self.image, "sleep", "infinity"], "starting the environment")
            # The work folders are made inside the container: `docker cp` into a
            # path that does not exist there fails, and a host mount is exactly
            # what this environment must not have.
            self._must(["exec", container, "mkdir", "-p", IN_DIR, OUT_DIR],
                       "preparing the environment's work folder")
            for name, build_source in SOURCES.items():
                source = incoming / name
                source.write_text(build_source(topic), encoding="utf-8")
                job.sources[name] = source
                self._must(["cp", _docker_path(source), f"{container}:{IN_DIR}/{name}"],
                           f"copying {name} into the environment")

            for name in SOURCES:
                for fmt in (CONVERSIONS[name][0], "pdf"):
                    step = self._convert(job, name, fmt)
                    if step.exit_code != 0:
                        raise OfficeError("conversion_failed",
                                          f"soffice could not write {fmt} from {name}: {step.output[-200:]}")

            listing = self._must(["exec", container, "ls", "-1", OUT_DIR],
                                 "reading the environment's own listing")
            job.listing = listing.strip()
            job.listing_files = tuple(line.strip() for line in listing.splitlines() if line.strip())
            job.steps.append(Step(name="evidence", command=(self.docker, "exec", container, "ls"),
                                  exit_code=0, output=job.listing))

            for name in job.listing_files:
                self._must(["cp", f"{container}:{OUT_DIR}/{name}",
                            _docker_path(produced / name)],
                           f"copying {name} out of the environment")

            for name in sorted(job.listing_files):
                path = produced / name
                if not path.is_file():
                    raise OfficeError("artifact_missing", f"{name} was listed but did not come out")
                pages, reason = (pdf_pages(path) if path.suffix.lower() == ".pdf" else (None, ""))
                job.artifacts.append(Artifact(name=name, path=path, bytes=path.stat().st_size,
                                              sha256=_digest(path), pages=pages,
                                              pages_reason=reason))
            return job
        finally:
            self._run(["rm", "-f", container])
            job.stopped = True

    def _convert(self, job: OfficeJob, name: str, fmt: str) -> Step:
        argv = ["exec", job.container, "soffice", "--headless", "--norestore", "--nolockcheck",
                "--convert-to", fmt, "--outdir", OUT_DIR, f"{IN_DIR}/{name}"]
        try:
            code, out, err = self._run(argv)
        except OfficeError as exc:
            code, out, err = 1, "", f"{exc.code}: {exc.reason}"
        step = Step(name=f"{name}->{fmt}", command=(self.docker, *argv), exit_code=code,
                    output=(err or out).strip()[-400:])
        job.steps.append(step)
        return step


# -------------------------------------------------------------- the records


def _action_for(job: OfficeJob, step: Step) -> Action:
    outcome = EffectOutcome.SUCCEEDED if step.exit_code == 0 else EffectOutcome.FAILED
    return Action(id=step.record_id or uuid.uuid4().hex, state=State.COMPLETED,
                  provenance=Provenance.OBSERVATION,
                  tool="office.env", arguments={"step": step.name, "argv": list(step.command)[1:]},
                  effect=Effect(kind="command.run", target=job.container, outcome=outcome,
                                observed_at=now()),
                  result=step.output[-400:], decision="allow",
                  labels=("office", "isolated"))


def publish(job: OfficeJob, *, stream: str = DEMO_STREAM, worker: Any | None = None) -> tuple[str, ...]:
    """Publish one `Action` per step and one `Experience` for the job.

    The stream is named explicitly and defaults to the demo stream, so a demo can
    never write into the stream the owner's own work lives in. `worker` is
    injectable so the record shape can be tested without a graph.
    """
    if not job.steps:
        raise OfficeError("nothing_to_record", "the job has no steps, so there is nothing to record")
    if worker is None:
        host, port = str(config.value("graph.host")), int(config.value("graph.port"))
        worker = GraphWorker(f"ws://{host}:{port}/ws_json", stream,
                             config.data_root() / "graph-writer.lock")

    async def _publish() -> tuple[str, ...]:
        try:
            published: list[str] = []
            steps: list[Step] = []
            for step in job.steps:
                record = _action_for(job, step)
                await worker.call("append", record=record.to_dict(), operation_id=record.id)
                published.append(record.id)
                steps.append(replace(step, record_id=record.id))
            job.steps = steps
            summary = Experience(
                id=uuid.uuid4().hex, state=State.COMPLETED, provenance=Provenance.OBSERVATION,
                summary=f"офисная работа в изолированной среде: {job.topic}",
                lesson="документ, таблица и презентация собраны контейнером; файлы вынесены копированием",
                score=None, verified=bool(job.artifacts),
                labels=("office", "isolated", f"job:{job.id}"))
            await worker.call("append", record=summary.to_dict(), operation_id=summary.id)
            published.append(summary.id)
            return tuple(published)
        finally:
            await worker.close()

    try:
        return asyncio.run(_publish())
    except Exception as exc:                      # a graph that refused is not a silent success
        raise OfficeError("not_recorded",
                          f"the graph did not accept the records ({exc.__class__.__name__}: {exc})") from None


def run_job(topic: str, *, out_dir: Path | None = None, stream: str = DEMO_STREAM,
            sandbox: Sandbox | None = None, record: bool = True) -> OfficeJob:
    """The whole job: sources, the container's work, the files out, and the records."""
    job = (sandbox or Sandbox()).run(topic, out_dir=out_dir)
    if record:
        job.records = publish(job, stream=stream)
    return job


def report(job: OfficeJob) -> dict[str, Any]:
    """What the job claims, with the evidence it claims it from."""
    return {"job": job.to_dict(),
            "environment": {"image": job.image, "container": job.container, "stopped": job.stopped,
                            "listing": job.listing},
            "records": list(job.records),
            "note": "files were produced inside the container and copied out; "
                    "the listing above was read inside it"}
