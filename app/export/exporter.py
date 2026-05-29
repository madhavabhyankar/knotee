from datetime import datetime
from pathlib import Path
from typing import Optional

from ..storage.models import Meeting


def to_txt(meeting: Meeting, path: str) -> None:
    lines = [
        f"Meeting: {meeting.title}",
        f"Date: {meeting.started_at.strftime('%B %d, %Y %H:%M')}",
        "",
    ]
    if meeting.summary:
        lines += ["── Summary ──", meeting.summary, ""]
    if meeting.action_items:
        lines += ["── Action Items ──", meeting.action_items, ""]
    lines.append("── Transcript ──")
    for seg in meeting.segments:
        speaker = seg.speaker_display or "Unknown"
        ts = _fmt_sec(seg.start_sec)
        lines.append(f"[{ts}] {speaker}: {seg.text}")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def to_pdf(meeting: Meeting, path: str) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    doc = SimpleDocTemplate(path, pagesize=letter,
                            leftMargin=inch, rightMargin=inch,
                            topMargin=inch, bottomMargin=inch)
    styles = getSampleStyleSheet()
    title_style = styles["Title"]
    h2_style = styles["Heading2"]
    body_style = styles["BodyText"]
    speaker_style = ParagraphStyle(
        "Speaker",
        parent=body_style,
        fontName="Helvetica-Bold",
        fontSize=9,
    )
    ts_style = ParagraphStyle(
        "TS",
        parent=body_style,
        fontName="Courier",
        fontSize=8,
        textColor=(0.5, 0.5, 0.5),
    )

    story = [
        Paragraph(meeting.title, title_style),
        Paragraph(meeting.started_at.strftime("%B %d, %Y %H:%M"), body_style),
        Spacer(1, 0.2 * inch),
    ]

    if meeting.summary:
        story += [Paragraph("Summary", h2_style),
                  Paragraph(meeting.summary.replace("\n", "<br/>"), body_style),
                  Spacer(1, 0.15 * inch)]

    if meeting.action_items:
        story += [Paragraph("Action Items", h2_style),
                  Paragraph(meeting.action_items.replace("\n", "<br/>"), body_style),
                  Spacer(1, 0.15 * inch)]

    story.append(Paragraph("Transcript", h2_style))
    for seg in meeting.segments:
        speaker = seg.speaker_display or "Unknown"
        ts = _fmt_sec(seg.start_sec)
        story.append(Paragraph(f"[{ts}] <b>{speaker}:</b> {seg.text}", body_style))
        story.append(Spacer(1, 0.05 * inch))

    doc.build(story)


def _fmt_sec(secs: float) -> str:
    m, s = divmod(int(secs), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
