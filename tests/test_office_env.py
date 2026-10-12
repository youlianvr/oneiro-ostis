"""The isolated office environment: sources, one job, its refusals, its records.

Docker is not needed here: `Sandbox` takes its command runner, so the fake below
plays the container, keeps its own `/work/out` and answers `docker cp` from that
store. What the real container does is proved separately by running the command
against Docker; what these tests hold is the orchestration around it — that every
source is converted, that the listing comes from inside, that the container is
removed even when a conversion fails, and that each step becomes one record.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from oneiro import office_env


class FakeDocker:
    """A container that keeps `/work/out` and copies out of it."""

    def __init__(self, *, fail_on: str = "", image_present: bool = True) -> None:
        self.commands: list[list[str]] = []
        self.store: dict[str, bytes] = {}
        self.fail_on = fail_on
        self.image_present = image_present
        self.removed = False

    def __call__(self, argv: list[str], *, timeout: float = 0.0) -> tuple[int, str, str]:
        self.commands.append(argv)
        _, *rest = argv
        if rest[0] == "image":
            return (0, "sha256:fake\n", "") if self.image_present else (1, "", "No such image")
        if rest[0] == "build":
            self.image_present = True
            return 0, "Successfully tagged", ""
        if rest[0] == "run":
            return 0, "container-id\n", ""
        if rest[0] == "rm":
            self.removed = True
            return 0, rest[-1] + "\n", ""
        if rest[0] == "cp":
            source, destination = rest[1], rest[2]
            # A container source is named, not a Windows path: `C:` would be read
            # as a container prefix by anything that only looks for a colon.
            if source.startswith("oneiro-office-"):     # out of the container
                name = source.split(":", 1)[1].rsplit("/", 1)[-1]
                Path(destination).write_bytes(self.store[name])
            else:                                       # into the container
                name = Path(source).name
                self.store["in/" + name] = Path(source).read_bytes() if Path(source).is_file() else b""
            return 0, "", ""
        if rest[0] == "exec":
            # `docker exec <container> <command …>`: the container is rest[1].
            if rest[2] == "mkdir":
                return 0, "", ""
            if rest[2] == "ls":
                if self.fail_on == "ls":
                    return 1, "", "ls: cannot access '/work/out'"
                listing = sorted(name for name in self.store
                                 if not name.startswith("in/")
                                 and name.endswith((".odt", ".xlsx", ".pptx", ".pdf")))
                return 0, "\n".join(listing) + "\n", ""
            convert_to = rest[rest.index("--convert-to") + 1]
            source = Path(rest[-1]).name
            stem = source.rsplit(".", 1)[0]
            if self.fail_on == convert_to or self.fail_on == source:
                return 1, "", "Error: source file could not be loaded"
            if convert_to == "pdf":
                # A one-page stand-in: what the page count is measured from is the
                # real suite's output, and this only exercises the copy-out path.
                self.store[f"{stem}.pdf"] = b"%PDF-1.4\n%%EOF\n"
            else:
                self.store[f"{stem}.{office_env.CONVERSIONS[source][1].lstrip('.')}"] = b"binary\x00"
            return 0, f"convert {source} -> {convert_to}", ""
        return 1, "", f"unexpected command: {argv}"


def _sandbox(fake: FakeDocker) -> office_env.Sandbox:
    return office_env.Sandbox(runner=fake, docker="docker")


def test_the_sources_are_flat_odf_with_the_topic_in_them(tmp_path):
    assert set(office_env.SOURCES) == {"note.fodt", "table.fods", "slides.fodp"}
    text = office_env.document_source("Отчёт <черновик>")
    sheet = office_env.spreadsheet_source("Отчёт")
    slides = office_env.presentation_source("Отчёт")
    assert 'office:mimetype="application/vnd.oasis.opendocument.text"' in text
    assert 'office:mimetype="application/vnd.oasis.opendocument.spreadsheet"' in sheet
    assert 'office:mimetype="application/vnd.oasis.opendocument.presentation"' in slides
    assert "Отчёт &lt;черновик&gt;" in text, "the topic is escaped, not pasted raw"
    assert "Отчёт" in slides


def test_one_job_converts_every_source_and_takes_the_files_out(tmp_path):
    fake = FakeDocker()
    job = _sandbox(fake).run("Проверка", out_dir=tmp_path)

    names = sorted(item.name for item in job.artifacts)
    assert names == ["note.odt", "note.pdf", "slides.pdf", "slides.pptx", "table.pdf", "table.xlsx"]
    assert sorted(job.sources) == ["note.fodt", "slides.fodp", "table.fods"]
    for item in job.artifacts:
        assert item.bytes > 0 and len(item.sha256) == 64
        assert item.path.parent == job.workdir / "out"
    assert job.listing_files == tuple(names), "the evidence is the container's own listing"
    assert job.stopped is True and fake.removed is True
    runs = [command for command in fake.commands if command[1:2] == ["run"]]
    assert runs and "--network" in runs[0] and "none" in runs[0], \
        "the environment runs without a network"


def test_a_failed_conversion_is_a_named_refusal_and_the_container_still_goes(tmp_path):
    fake = FakeDocker(fail_on="pptx")
    with pytest.raises(office_env.OfficeError) as caught:
        _sandbox(fake).run("Проверка", out_dir=tmp_path)
    assert caught.value.code == "conversion_failed"
    assert "slides.fodp" in caught.value.reason
    assert fake.removed is True, "a failed job must not leave a container behind"


def test_a_missing_image_is_named_instead_of_built_over_an_absent_file(tmp_path):
    fake = FakeDocker(image_present=False)
    sandbox = _sandbox(fake)
    with pytest.raises(office_env.OfficeError) as caught:
        sandbox.ensure_image(build=False)
    assert caught.value.code == "image_absent"
    assert "oneiro office image" in caught.value.reason, "the refusal says how to fix it"

    built = sandbox.ensure_image()
    assert built == office_env.IMAGE
    assert any(c[:2] == ["docker", "build"] for c in fake.commands)


def test_a_build_that_outlived_its_client_is_not_reported_as_a_failure():
    class SlowDocker(FakeDocker):
        def __call__(self, argv: list[str], *, timeout: float = 0.0) -> tuple[int, str, str]:
            result = super().__call__(argv, timeout=timeout)
            if argv[1:2] == ["build"]:
                self.image_present = True               # the daemon finished the job
                return 1, "", "context deadline exceeded"  # the client gave up first
            return result

    fake = SlowDocker(image_present=False)
    assert office_env.Sandbox(runner=fake, docker="docker").ensure_image() == office_env.IMAGE, \
        "the image that exists is the evidence, not the exit status of the build client"


def test_an_absent_dockerfile_is_named(tmp_path):
    sandbox = office_env.Sandbox(runner=FakeDocker(), docker="docker",
                                 dockerfile=tmp_path / "missing" / "Dockerfile")
    with pytest.raises(office_env.OfficeError) as caught:
        sandbox.build()
    assert caught.value.code == "dockerfile_absent"


def test_pdf_pages_are_measured_or_the_reason_is_given(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    pages, reason = office_env.pdf_pages(broken)
    assert pages is None and reason, "an unreadable PDF is reported, never counted as zero"


def test_every_step_becomes_one_action_in_the_demo_stream(tmp_path):
    fake = FakeDocker()
    job = _sandbox(fake).run("Проверка", out_dir=tmp_path)

    class StubWorker:
        def __init__(self) -> None:
            self.calls: list[dict] = []
            self.closed = False

        async def call(self, operation: str, **arguments):
            self.calls.append({"operation": operation, **arguments})
            return {"ok": True}

        async def close(self) -> None:
            self.closed = True

    stub = StubWorker()
    published = office_env.publish(job, worker=stub)

    actions = [call for call in stub.calls if call["record"]["kind"] == "action"]
    assert len(actions) == len(job.steps) == 7, "six conversions and one evidence read"
    assert published[:len(job.steps)] == tuple(step.record_id for step in job.steps)
    assert len(published) == len(job.steps) + 1, "one record per step and one for the job"
    assert all(call["operation"] == "append" for call in stub.calls)
    kinds = [call["record"]["kind"] for call in stub.calls]
    assert kinds[-1] == "experience" and kinds.count("experience") == 1
    for call in actions:
        record = call["record"]
        assert record["decision"] == "allow"
        assert record["effect"]["outcome"] == "succeeded"
        assert record["labels"] == ["office", "isolated"]
    assert stub.closed is True


def test_a_job_with_no_steps_is_not_recorded(tmp_path):
    job = office_env.OfficeJob(id="0" * 12, topic="t", image=office_env.IMAGE,
                               container="c", workdir=tmp_path, sources={})
    with pytest.raises(office_env.OfficeError) as caught:
        office_env.publish(job, worker=object())
    assert caught.value.code == "nothing_to_record"


def test_the_demo_stream_is_not_the_products_stream():
    assert office_env.DEMO_STREAM == "demo"
    assert office_env.DEMO_STREAM != "product", "demo records must not mix into the owner's stream"
