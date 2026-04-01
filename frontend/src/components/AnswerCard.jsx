import { useEffect, useRef, useState } from "react";
import { getMilestoneDeliverables } from "../api";

function toTitleCase(value) {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") {
    return "Not provided";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toLocaleString();
  }
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return new Date(value).toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "numeric" });
  }
  return String(value);
}

function countUnique(answer, field) {
  return new Set(answer.map((row) => row[field]).filter(Boolean)).size;
}

function hasAnyFilter(filters, fields) {
  return filters?.some((item) => fields.includes(item.field));
}

function queryStartsWith(query, prefixes) {
  return prefixes.some((prefix) => query.startsWith(prefix));
}

function groupRowsByEntity(answer) {
  const groups = new Map();
  answer.forEach((row) => {
    const key = `${row.car_family ?? ""}|${row.commercial_name ?? ""}|${row.brand ?? ""}`;
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(row);
  });
  return [...groups.values()];
}

function extractMatchedComponents(filters) {
  return (filters ?? [])
    .filter((item) => ["tcu_details", "infotainment_details", "ota", "eea", "architecture"].includes(item.field))
    .map((item) => ({ field: item.field, value: item.value }));
}

function buildMilestones(row) {
  const anchorLabel = row.milestone_anchor_label || "SOPM";
  const anchorValue = row.milestone_anchor_date || row.sopm || row.launch_date;
  const items = [
    { label: "IM", value: row.milestone_im },
    { label: "PM", value: row.milestone_pm },
    { label: "CM", value: row.milestone_cm },
    { label: "DM", value: row.milestone_dm },
    { label: "SHRM", value: row.milestone_shrm },
    { label: "X0", value: row.milestone_x0 },
    { label: "X1", value: row.milestone_x1 },
    { label: "SOP-8", value: row.milestone_sop_8 },
    { label: "SOP-6", value: row.milestone_sop_6 },
    { label: "X2", value: row.milestone_x2 },
    { label: "SOP-3", value: row.milestone_sop_3 },
    { label: "LRM", value: row.milestone_lrm },
    { label: "X3", value: row.milestone_x3 },
    { label: anchorLabel, value: anchorValue },
    ...(anchorLabel === "MCA" ? [] : [{ label: "MCA", value: row.mca_sopm }]),
    ...(anchorLabel === "MCA2" ? [] : [{ label: "MCA2", value: row.mca2_sopm }]),
    ...(anchorLabel === "SOPM" ? [] : [{ label: "SOPM", value: row.sopm || row.launch_date }]),
    { label: "EOP", value: row.eop },
  ].filter((item) => item.value);
  return items;
}

const BRIEF_MILESTONE_SEQUENCE = [
  { label: "IM", field: "milestone_im", code: "POST_IM" },
  { label: "PM", field: "milestone_pm", code: "PM" },
  { label: "CM", field: "milestone_cm", code: "CM" },
  { label: "SHRM", field: "milestone_shrm", code: "SHRM" },
  { label: "X0", field: "milestone_x0", code: "X0" },
  { label: "SOP-8", field: "milestone_sop_8", code: "SOP_8" },
  { label: "SOP-6", field: "milestone_sop_6", code: "SOP_6" },
  { label: "SOP-3", field: "milestone_sop_3", code: "SOP_3" },
  { label: "LRM", field: "milestone_lrm", code: "LRM" },
  { label: "SOPM", field: "milestone_anchor_date", code: "SOPM" },
];

function milestoneLabelToCode(label) {
  return String(label || "")
    .trim()
    .toUpperCase()
    .replace(/\s*-\s*/g, "_")
    .replace(/[^A-Z0-9_]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

function parseIsoDate(value) {
  if (!value || typeof value !== "string") {
    return null;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function extractUniqueValues(rows, field) {
  return [...new Set(rows.map((row) => row[field]).filter(Boolean))];
}

function formatList(values) {
  const unique = [...new Set(values.filter(Boolean))];
  if (unique.length === 0) {
    return "";
  }
  if (unique.length === 1) {
    return unique[0];
  }
  if (unique.length === 2) {
    return `${unique[0]} and ${unique[1]}`;
  }
  return `${unique.slice(0, -1).join(", ")}, and ${unique.at(-1)}`;
}

function joinSentence(parts) {
  return parts.filter(Boolean).join(" ");
}

function formatLaunchStageLabel(value) {
  if (value === "MCA") {
    return "MCA1";
  }
  return value || "Launch";
}

function resolveRelevantLaunch(rows) {
  const now = new Date();
  const candidates = rows
    .flatMap((row) => [
      { label: "SOPM", value: row.sopm },
      { label: "MCA", value: row.mca_sopm },
      { label: "MCA2", value: row.mca2_sopm },
    ])
    .map((item) => ({ ...item, date: parseIsoDate(item.value) }))
    .filter((item) => item.date);

  const future = candidates
    .filter((item) => item.date >= now)
    .sort((left, right) => left.date - right.date);
  if (future.length > 0) {
    return future[0];
  }
  return candidates.sort((left, right) => right.date - left.date)[0] ?? null;
}

function buildVehicleSummary(rows) {
  const head = rows[0];
  const launch = resolveRelevantLaunch(rows);
  const responsibleRegion = extractUniqueValues(rows, "project_responsible_region");
  const salesRegions = extractUniqueValues(rows, "region_of_sales");
  const eeaValues = extractUniqueValues(rows, "eea");
  const tcuValues = extractUniqueValues(rows, "tcu_details");
  const infotainmentValues = extractUniqueValues(rows, "infotainment_details");

  const opening = joinSentence([
    `The ${head.car_family} car family`,
    head.brand && head.commercial_name ? `(${head.brand} - ${head.commercial_name})` : "",
    responsibleRegion.length ? `is managed within the ${formatList(responsibleRegion)} region` : "",
    launch ? `with ${launch.label} aligned to ${formatValue(launch.value)}.` : ".",
  ]);

  const programSentence = joinSentence([
    head.car_family ? `${head.car_family}` : "This vehicle",
    head.program ? `is part of the ${head.program} vehicle program` : "",
    eeaValues.length ? `and is configured on ${formatList(eeaValues)}` : "",
    tcuValues.length ? `with ${formatList(tcuValues)}` : "",
    infotainmentValues.length ? `paired with ${formatList(infotainmentValues)} infotainment.` : ".",
  ]);

  const regionSentence = salesRegions.length
    ? `Target sales coverage includes ${formatList(salesRegions)}.`
    : "";

  return joinSentence([opening, programSentence, regionSentence]).replace(/\s+\./g, ".");
}

function buildVehicleDetails(rows) {
  const head = rows[0];
  return [
    { label: "Car Family", value: head.car_family },
    { label: "Brand", value: head.brand },
    { label: "Commercial Name", value: head.commercial_name },
    { label: "EEA", value: formatList(extractUniqueValues(rows, "eea")) },
    { label: "TCU", value: formatList(extractUniqueValues(rows, "tcu_details")) },
    { label: "Infotainment", value: formatList(extractUniqueValues(rows, "infotainment_details")) },
    { label: "Powertrain", value: formatList(extractUniqueValues(rows, "powertrain")) },
    { label: "Platform", value: formatList(extractUniqueValues(rows, "platform")) },
    { label: "Program", value: formatList(extractUniqueValues(rows, "program")) },
    { label: "OTA", value: formatList(extractUniqueValues(rows, "ota")) },
  ].filter((item) => item.value);
}

function buildLaunchBriefRows(rows) {
  const groups = new Map();

  rows.forEach((row) => {
    const launch = resolveRelevantLaunch([row]);
    const key = [
      row.car_family || "",
      row.brand || "",
      row.commercial_name || "",
      row.eea || "",
      row.tcu_details || "",
      row.region_of_sales || "",
      row.initial_prod_zone || "",
      launch?.label || "",
      launch?.value || "",
    ].join("|");

    if (!groups.has(key)) {
      groups.set(key, {
        head: row,
        launch,
        rows: [],
      });
    }
    groups.get(key).rows.push(row);
  });

  return [...groups.values()];
}

function buildGroupedLaunchWindowRows(rows) {
  const groups = new Map();

  rows.forEach((row) => {
    const eventDate = row.launch_date || row.sopm || "";
    const eventLabel = row.launch_stage || "SOPM";
    const key = [
      row.car_family || "",
      row.brand || "",
      row.commercial_name || "",
      eventLabel,
      eventDate,
      row.initial_prod_zone || "",
      row.eea || "",
      row.tcu_details || "",
      row.infotainment_details || "",
      row.ota || "",
      row.platform || "",
      row.program || "",
    ].join("|");

    if (!groups.has(key)) {
      groups.set(key, {
        head: row,
        rows: [],
      });
    }
    groups.get(key).rows.push(row);
  });

  return [...groups.values()]
    .sort((left, right) => {
      const leftDate = parseIsoDate(left.head.launch_date || left.head.sopm)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      const rightDate = parseIsoDate(right.head.launch_date || right.head.sopm)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      if (leftDate !== rightDate) {
        return leftDate - rightDate;
      }
      return String(left.head.commercial_name || left.head.car_family || "").localeCompare(
        String(right.head.commercial_name || right.head.car_family || "")
      );
    })
    .map((group) => ({
      ...group,
      salesRegions: extractUniqueValues(group.rows, "region_of_sales"),
    }));
}

function renderLaunchWindowCardGrid(answer) {
  const groups = buildGroupedLaunchWindowRows(answer);
  return (
    <div className="card-grid">
      {groups.map((group, index) => {
        const head = group.head;
        const currentMilestone = buildLaunchWindowCurrentMilestone(head);
        const eventDate = head.launch_date || head.sopm;
        const eventLabel = head.launch_stage || "SOPM";
        return (
          <article className="launch-card launch-window-card" key={`${head.car_family ?? "launch"}-${eventDate ?? index}-${eventLabel}`}>
            <div className="launch-card-top launch-window-top">
              <div className="launch-window-identity">
                <strong className="launch-window-family">{head.car_family || "Unknown"}</strong>
                <p className="launch-window-name">{[head.brand, head.commercial_name].filter(Boolean).join(" ") || "Commercial name not provided"}</p>
                <p className="launch-window-ipz">{head.initial_prod_zone || "IPZ not provided"}</p>
              </div>
              <div className="launch-window-date">
                <span>{formatLaunchStageLabel(eventLabel)}</span>
                <strong>{formatValue(eventDate)}</strong>
              </div>
            </div>
            <dl className="card-facts launch-window-facts">
              <div>
                <dt>RoS</dt>
                <dd>{formatList(group.salesRegions) || "Not provided"}</dd>
              </div>
              <div>
                <dt>EEA</dt>
                <dd>{head.eea || "Not provided"}</dd>
              </div>
              <div>
                <dt>TCU</dt>
                <dd>{head.tcu_details || "Not provided"}</dd>
              </div>
              <div>
                <dt>Infotainment</dt>
                <dd>{head.infotainment_details || "Not provided"}</dd>
              </div>
              <div>
                <dt>OTA</dt>
                <dd>{head.ota || "Not provided"}</dd>
              </div>
              <div>
                <dt>Platform</dt>
                <dd>{head.platform || "Not provided"}</dd>
              </div>
              <div>
                <dt>Current Milestone</dt>
                <dd>{currentMilestone ? `${currentMilestone.label} (${formatValue(currentMilestone.date)})` : "Not provided"}</dd>
              </div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function canRenderSharedVehicleCards(rows) {
  return Array.isArray(rows) &&
    rows.length > 0 &&
    rows.every((row) => row && typeof row === "object") &&
    rows.some((row) => row.car_family || row.commercial_name || row.brand);
}

function buildComponentMatchCardGroups(rows) {
  return groupRowsByEntity(rows)
    .map((groupRows) => {
      const sortedRows = [...groupRows].sort((left, right) => {
        const leftDate = parseIsoDate(left.sopm)?.getTime() ?? Number.MAX_SAFE_INTEGER;
        const rightDate = parseIsoDate(right.sopm)?.getTime() ?? Number.MAX_SAFE_INTEGER;
        if (leftDate !== rightDate) {
          return leftDate - rightDate;
        }
        return String(left.commercial_name || left.car_family || "").localeCompare(
          String(right.commercial_name || right.car_family || "")
        );
      });

      return {
        head: sortedRows[0],
        rows: sortedRows,
        salesRegions: extractUniqueValues(sortedRows, "region_of_sales"),
      };
    })
    .sort((left, right) => {
      const leftDate = parseIsoDate(left.head?.sopm)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      const rightDate = parseIsoDate(right.head?.sopm)?.getTime() ?? Number.MAX_SAFE_INTEGER;
      if (leftDate !== rightDate) {
        return leftDate - rightDate;
      }
      return String(left.head?.commercial_name || left.head?.car_family || "").localeCompare(
        String(right.head?.commercial_name || right.head?.car_family || "")
      );
    });
}

function renderComponentMatchCardGrid(answer) {
  const groups = buildComponentMatchCardGroups(answer);

  return (
    <div className="card-grid">
      {groups.map((group, index) => {
        const head = group.head;
        const currentMilestone = buildLaunchWindowCurrentMilestone(head);
        return (
          <article className="launch-card launch-window-card" key={`${head.car_family ?? "component"}-${head.sopm ?? index}`}>
            <div className="launch-card-top launch-window-top">
              <div className="launch-window-identity">
                <strong className="launch-window-family">{head.car_family || "Unknown"}</strong>
                <p className="launch-window-name">{[head.brand, head.commercial_name].filter(Boolean).join(" ") || "Commercial name not provided"}</p>
                <p className="launch-window-ipz">{head.initial_prod_zone || "IPZ not provided"}</p>
              </div>
              <div className="launch-window-date">
                <span>SOPM</span>
                <strong>{formatValue(head.sopm)}</strong>
              </div>
            </div>
            <dl className="card-facts launch-window-facts">
              <div>
                <dt>RoS</dt>
                <dd>{formatList(group.salesRegions) || "Not provided"}</dd>
              </div>
              <div>
                <dt>EEA</dt>
                <dd>{head.eea || "Not provided"}</dd>
              </div>
              <div>
                <dt>TCU</dt>
                <dd>{head.tcu_details || "Not provided"}</dd>
              </div>
              <div>
                <dt>Infotainment</dt>
                <dd>{head.infotainment_details || "Not provided"}</dd>
              </div>
              <div>
                <dt>OTA</dt>
                <dd>{head.ota || "Not provided"}</dd>
              </div>
              <div>
                <dt>Platform</dt>
                <dd>{head.platform || "Not provided"}</dd>
              </div>
              <div>
                <dt>Current Milestone</dt>
                <dd>{currentMilestone ? `${currentMilestone.label} (${formatValue(currentMilestone.date)})` : "Not provided"}</dd>
              </div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function determineCurrentMilestone(row) {
  const now = new Date();
  const milestones = BRIEF_MILESTONE_SEQUENCE.map((item) => ({
    ...item,
    value: row[item.field],
    date: parseIsoDate(row[item.field]),
  })).filter((item) => item.date);

  if (milestones.length === 0) {
    return null;
  }

  const completed = milestones.filter((item) => item.date <= now);
  if (completed.length > 0) {
    return completed.sort((left, right) => right.date - left.date)[0];
  }
  return milestones.sort((left, right) => left.date - right.date)[0];
}

function buildLaunchWindowCurrentMilestone(row) {
  const current = determineCurrentMilestone(row);
  if (!current) {
    return null;
  }
  return {
    label: current.label,
    date: row[current.field],
  };
}

function buildCurrentAndUpcomingMilestones(row, deliverables) {
  const now = new Date();
  const milestones = BRIEF_MILESTONE_SEQUENCE.map((item) => ({
    ...item,
    value: row[item.field],
    date: parseIsoDate(row[item.field]),
  })).filter((item) => item.date);
  if (milestones.length === 0) {
    return { current: null, upcoming: null };
  }
  const completed = milestones.filter((item) => item.date <= now).sort((left, right) => right.date - left.date);
  const future = milestones.filter((item) => item.date > now).sort((left, right) => left.date - right.date);
  const current = completed[0] ?? milestones[0];
  const upcoming = future[0] ?? milestones[milestones.length - 1];
  return {
    current: current
      ? {
          label: current.label,
          date: row[current.field],
          deliverableCode: milestoneLabelToCode(current.label),
          deliverable: deliverables.find((item) => item.milestone_code === milestoneLabelToCode(current.label)),
        }
      : null,
    upcoming: upcoming
      ? {
          label: upcoming.label,
          date: row[upcoming.field],
          deliverableCode: milestoneLabelToCode(upcoming.label),
          deliverable: deliverables.find((item) => item.milestone_code === milestoneLabelToCode(upcoming.label)),
        }
      : null,
  };
}

function renderVehicleImage(head) {
  return <VehicleImage brand={head.brand} commercialName={head.commercial_name} />;
}

function VehicleImage({ brand, commercialName }) {
  const [imageUrl, setImageUrl] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function loadImage() {
      const queries = [
        [brand, commercialName].filter(Boolean).join(" "),
        commercialName,
        brand,
      ].filter(Boolean);

      for (const query of queries) {
        try {
          const response = await fetch(
            `https://en.wikipedia.org/w/api.php?action=query&format=json&origin=*&generator=search&gsrsearch=${encodeURIComponent(query)}&gsrlimit=6&prop=pageimages|extracts&piprop=original&exintro=1&explaintext=1`
          );
          if (!response.ok) {
            continue;
          }
          const payload = await response.json();
          const pages = Object.values(payload?.query?.pages ?? {});
          const name = (commercialName || "").toLowerCase();
          const brandName = (brand || "").toLowerCase();
          const match = pages.find((page) => {
            if (!page?.original?.source) {
              return false;
            }
            const title = String(page.title || "").toLowerCase();
            const extract = String(page.extract || "").toLowerCase();
            const titleMatch = name && (title.includes(name) || name.includes(title));
            const extractMatch = name && extract.includes(name);
            const brandMatch = !brandName || title.includes(brandName) || extract.includes(brandName);
            return (titleMatch || extractMatch) && brandMatch;
          });
          if (match?.original?.source) {
            if (!cancelled) {
              setImageUrl(match.original.source);
            }
            return;
          }
        } catch {
          // Ignore lookup failures and fall back to the branded placeholder.
        }
      }
    }

    setImageUrl("");
    loadImage();
    return () => {
      cancelled = true;
    };
  }, [brand, commercialName]);

  if (imageUrl) {
    return <img className="vehicle-hero-image" src={imageUrl} alt={`${brand || ""} ${commercialName || "vehicle"}`.trim()} />;
  }

  return (
    <div className="vehicle-hero-fallback">
      <span>{brand?.[0] || commercialName?.[0] || "V"}</span>
    </div>
  );
}

function renderMilestoneStrip(row) {
  const milestones = buildMilestones(row);
  if (milestones.length === 0) {
    return null;
  }

  return (
    <div className="milestone-strip compact-milestones">
      {milestones.map((item) => (
        <div className="milestone-node" key={`${item.label}-${item.value}`}>
          <span>{item.label}</span>
          <strong>{formatValue(item.value)}</strong>
        </div>
      ))}
    </div>
  );
}

function renderMilestoneTimeline(row, highlightedLabel) {
  return <MilestoneTimeline row={row} highlightedLabel={highlightedLabel} />;
}

function MilestoneTimeline({ row, highlightedLabel }) {
  const timelineItems = BRIEF_MILESTONE_SEQUENCE.map((item) => ({
    label: item.label,
    value: row[item.field],
    date: parseIsoDate(row[item.field]),
  })).filter((item) => item.value);
  const listRef = useRef(null);
  const itemRefs = useRef([]);
  const [markerLeft, setMarkerLeft] = useState(0);

  if (timelineItems.length === 0) {
    return null;
  }

  const datedItems = timelineItems.filter((item) => item.date);
  const now = new Date();
  useEffect(() => {
    const listElement = listRef.current;
    if (!listElement || datedItems.length === 0) {
      setMarkerLeft(0);
      return;
    }

    const centers = datedItems.map((_, index) => {
      const item = itemRefs.current[index];
      if (!item) {
        return null;
      }
      return item.offsetLeft + item.offsetWidth / 2;
    });

    const validCenters = centers.filter((value) => value !== null);
    if (validCenters.length === 0) {
      setMarkerLeft(0);
      return;
    }

    if (datedItems.length === 1) {
      setMarkerLeft(validCenters[0]);
      return;
    }

    const milestoneIndex = datedItems.findIndex((item) => item.date >= now);
    const nextIndex = milestoneIndex === -1 ? datedItems.length - 1 : milestoneIndex;
    const prevIndex = nextIndex > 0 ? nextIndex - 1 : 0;
    const previous = datedItems[prevIndex];
    const next = datedItems[nextIndex];
    const prevCenter = centers[prevIndex] ?? validCenters[0];
    const nextCenter = centers[nextIndex] ?? validCenters.at(-1);

    if (!previous || !next || prevCenter === null || nextCenter === null) {
      setMarkerLeft(validCenters[0]);
      return;
    }

    if (milestoneIndex <= 0) {
      setMarkerLeft(prevCenter);
      return;
    }

    if (milestoneIndex === -1 || next.date <= previous.date) {
      setMarkerLeft(nextCenter);
      return;
    }

    const fraction = (now.getTime() - previous.date.getTime()) / (next.date.getTime() - previous.date.getTime());
    const clampedFraction = Math.min(Math.max(fraction, 0), 1);
    setMarkerLeft(prevCenter + (nextCenter - prevCenter) * clampedFraction);
  }, [datedItems, now]);

  return (
    <div className="milestone-timeline">
      <div className="milestone-timeline-track" />
      <div className="milestone-current-marker" style={{ left: `${markerLeft}px` }}>
        <span className="milestone-timeline-pointer" />
        <em>We&apos;re here</em>
      </div>
      <div className="milestone-timeline-list" ref={listRef}>
        {timelineItems.map((item, index) => {
          const isActive = item.label === highlightedLabel;
          return (
            <div
              className={`milestone-timeline-item${isActive ? " active" : ""}`}
              key={`${item.label}-${item.value}`}
              ref={(element) => {
                itemRefs.current[index] = element;
              }}
            >
              <span className="milestone-timeline-date">{formatValue(item.value)}</span>
              <div className="milestone-timeline-dot" />
              <strong className="milestone-timeline-label">{item.label}</strong>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function renderCount(answer) {
  return (
    <div className="count-answer">
      <span>Total distinct car families</span>
      <strong>{answer?.value ?? 0}</strong>
    </div>
  );
}

function renderMilestonePlan(answer, response) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No milestone-bearing rows matched the current plan.</p>;
  }

  const groups = groupRowsByEntity(answer);
  const requested = response?.plan?.milestone_columns ?? [];

  return (
    <div className="insight-stack">
      <div className="hero-insight">
        <span className="insight-kicker">Milestone Plan</span>
        <strong>{groups.length} matched vehicle profiles</strong>
        <p>{response.query}</p>
      </div>
      <div className="card-grid">
        {groups.map((rows) => {
          const head = rows[0];
          return (
            <article className="launch-card component-card" key={`${head.car_family}-${head.commercial_name}`}>
              <div className="launch-card-top">
                <strong>{head.commercial_name || head.car_family}</strong>
                <span>{head.milestone_anchor_label || "SOPM"} anchor</span>
              </div>
              <p>{[head.brand, head.car_family, head.platform].filter(Boolean).join(" / ")}</p>
              <div className="chip-row">
                {head.region_of_sales ? <span className="data-chip">{head.region_of_sales}</span> : null}
                {head.initial_prod_zone ? <span className="data-chip">{head.initial_prod_zone}</span> : null}
                {head.deliverable_milestone_label ? <span className="data-chip">{head.deliverable_milestone_label} deliverables</span> : null}
              </div>
              {renderMilestoneStrip(head)}
              {requested.length > 0 ? (
                <dl className="card-facts">
                  {requested.map((field) => (
                    head[field] ? (
                      <div key={field}>
                        <dt>{toTitleCase(field.replace("milestone_", ""))}</dt>
                        <dd>{formatValue(head[field])}</dd>
                      </div>
                    ) : null
                  ))}
                </dl>
              ) : null}
              {head.deliverable_milestone_label ? (
                <div className="deliverable-panel">
                  <h4>{head.deliverable_milestone_label} Deliverables</h4>
                  <div className="deliverable-grid">
                    <div className="entity-detail-card">
                      <span>Governance</span>
                      <strong>{head.deliverable_governance_communication || "Not provided"}</strong>
                    </div>
                    <div className="entity-detail-card">
                      <span>Readiness Objectives</span>
                      <strong>{head.deliverable_readiness_objectives || "Not provided"}</strong>
                    </div>
                    <div className="entity-detail-card">
                      <span>Timelines</span>
                      <strong>{head.deliverable_timelines || "Not provided"}</strong>
                    </div>
                    <div className="entity-detail-card">
                      <span>Risks</span>
                      <strong>{head.deliverable_risks || "Not provided"}</strong>
                    </div>
                    <div className="entity-detail-card">
                      <span>Escalation Path</span>
                      <strong>{head.deliverable_escalation_path || "Not provided"}</strong>
                    </div>
                    <div className="entity-detail-card">
                      <span>Ownership</span>
                      <strong>{head.deliverable_ownership || "Not provided"}</strong>
                    </div>
                  </div>
                </div>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}

function renderTable(answer) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No rows matched the current deterministic plan.</p>;
  }

  const columns = Object.keys(answer[0]);
  return (
    <div className="table-answer">
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column}>{toTitleCase(column)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {answer.map((row, index) => (
              <tr key={`${row.car_family ?? "row"}-${index}`}>
                {columns.map((column) => (
                  <td key={column}>{formatValue(row[column])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function renderDistribution(answer) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No grouped results available.</p>;
  }
  const max = Math.max(...answer.map((item) => item.value), 1);
  return (
    <div className="distribution-list">
      {answer.map((item, index) => {
        const label = Object.entries(item)
          .filter(([key]) => key !== "value")
          .map(([, value]) => formatValue(value))
          .join(" / ");
        return (
          <div className="distribution-row" key={`${label}-${index}`}>
            <div className="distribution-meta">
              <span>{label || "Result"}</span>
              <strong>{formatValue(item.value)}</strong>
            </div>
            <div className="distribution-bar">
              <div style={{ width: `${(item.value / max) * 100}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function renderOverlapCards(answer) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No overlap months were detected for the current constraints.</p>;
  }

  return (
    <div className="insight-stack">
      <div className="hero-insight">
        <span className="insight-kicker">Launch Load</span>
        <strong>{answer.length} overlap months found</strong>
        <p>The months below have multiple launch stages landing together.</p>
      </div>
      <div className="card-grid">
        {answer.map((row) => (
          <article className="launch-card overlap-card" key={row.launch_month}>
            <div className="launch-card-top">
              <strong>{row.launch_month}</strong>
              <span>{row.event_count} events</span>
            </div>
            <p>{row.stage_mix}</p>
            <div className="chip-row">
              <span className="data-chip">{row.stage_count} stages</span>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function renderBinaryResponse(answer, response) {
  const isPositive = Array.isArray(answer) && answer.length > 0;
  return (
    <div className="insight-stack">
      <div className={`hero-insight ${isPositive ? "positive-insight" : "negative-insight"}`}>
        <span className="insight-kicker">Deterministic Result</span>
        <strong>{isPositive ? "Yes, matching rows exist." : "No matching rows found."}</strong>
        <p>{response.query}</p>
      </div>
      {isPositive ? renderComponentMatch(answer, response, { compact: true }) : null}
    </div>
  );
}

function renderLaunchTimeline(answer, response) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return (
      <div className="hero-insight negative-insight">
        <span className="insight-kicker">Launch Timing</span>
        <strong>No launch rows matched.</strong>
        <p>{response.query}</p>
      </div>
    );
  }

  return (
    <div className="insight-stack">
      <div className="hero-insight">
        <span className="insight-kicker">Launch Timing</span>
        <strong>{countUnique(answer, "car_family")} vehicles matched</strong>
        <p>{response.query}</p>
      </div>
      <div className="timeline-list">
        {answer.map((row, index) => (
          <article className="timeline-card" key={`${row.car_family ?? "row"}-${row.region_of_sales ?? ""}-${index}`}>
            <div className="timeline-date">{formatValue(row.sopm ?? row.launch_date)}</div>
            <div className="timeline-body">
              <strong>{row.commercial_name || row.car_family}</strong>
              <p>{[row.brand, row.car_family].filter(Boolean).join(" / ")}</p>
              <div className="chip-row">
                {row.region_of_sales ? <span className="data-chip">{row.region_of_sales}</span> : null}
                {row.initial_prod_zone ? <span className="data-chip">{row.initial_prod_zone}</span> : null}
                {row.launch_stage ? <span className="data-chip">{row.launch_stage}</span> : null}
              </div>
              {renderMilestoneStrip(row)}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function renderLaunchWindow(answer, response) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return (
      <div className="hero-insight negative-insight">
        <span className="insight-kicker">Launch Window</span>
        <strong>No launch events matched.</strong>
        <p>{response.query}</p>
      </div>
    );
  }

  const groups = buildGroupedLaunchWindowRows(answer);
  return (
    <div className="insight-stack">
      <div className="hero-insight">
        <span className="insight-kicker">Launch Window</span>
        <strong>{groups.length} grouped launch events</strong>
        <p>{response.query}</p>
      </div>
      {renderLaunchWindowCardGrid(answer)}
    </div>
  );
}

function renderLaunchBrief(answer, response) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No launch rows matched the requested vehicle or region.</p>;
  }

  const groups = groupRowsByEntity(answer);
  return (
    <div className="insight-stack vehicle-brief-stack">
      <div className="hero-insight">
        <span className="insight-kicker">Launch Brief</span>
        <strong>{groups.length === 1 ? groups[0][0].commercial_name || groups[0][0].car_family : `${groups.length} matched vehicles`}</strong>
        <p>{response.query}</p>
      </div>
      {groups.map((rows) => {
        const head = rows[0];
        const launchRows = buildLaunchBriefRows(rows);
        const launch = resolveRelevantLaunch(rows);
        return (
          <section className="vehicle-brief launch-brief" key={`${head.car_family}-${head.commercial_name}`}>
            <div className="vehicle-hero">
              <div>
                <div className="vehicle-identity">
                  <h3>{head.car_family}</h3>
                  <p>{[head.brand, head.commercial_name].filter(Boolean).join(" - ")}</p>
                </div>
                <p className="launch-brief-summary">
                  {[head.car_family, head.brand, head.commercial_name].filter(Boolean).join(": ")}
                  {head.eea ? ` with ${head.eea}` : ""}
                  {head.tcu_details ? ` and ${head.tcu_details}` : ""}
                  {launch ? ` has ${launch.label} on ${formatValue(launch.value)}.` : ""}
                </p>
              </div>
              {renderVehicleImage(head)}
            </div>

            <section className="brief-section">
              <div className="brief-section-header">
                <span className="section-kicker">Launch Schedule</span>
              </div>
              <div className="launch-brief-list">
                {launchRows.map((item, index) => (
                  <article className="launch-brief-row" key={`${item.head.car_family}-${item.launch?.value || index}`}>
                    <div className="launch-brief-row-main">
                      <strong>
                        {[item.head.car_family, item.head.brand, item.head.commercial_name].filter(Boolean).join(": ")}
                      </strong>
                      <p>
                        {item.head.eea ? `${item.head.eea} - ` : ""}
                        {item.head.tcu_details || "TCU not provided"}
                      </p>
                    </div>
                    <div className="launch-brief-row-meta">
                      <span>{item.launch?.label || "Launch"}</span>
                      <strong>{formatValue(item.launch?.value)}</strong>
                    </div>
                    <div className="launch-brief-row-regions">
                      <div>
                        <span>Initial Production Zone</span>
                        <strong>{formatList(extractUniqueValues(item.rows, "initial_prod_zone")) || "Not provided"}</strong>
                      </div>
                      <div>
                        <span>Region of Sales</span>
                        <strong>{formatList(extractUniqueValues(item.rows, "region_of_sales")) || "Not provided"}</strong>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </section>
        );
      })}
    </div>
  );
}

function renderEntitySpotlight(answer, response) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No rows matched the requested vehicle profile.</p>;
  }

  const groups = groupRowsByEntity(answer);
  return (
    <VehicleBrief groups={groups} query={response.query} />
  );
}

function VehicleBrief({ groups, query }) {
  const [deliverables, setDeliverables] = useState([]);

  useEffect(() => {
    let cancelled = false;

    async function loadDeliverables() {
      try {
        const payload = await getMilestoneDeliverables();
        if (!cancelled) {
          setDeliverables(payload.items ?? []);
        }
      } catch {
        if (!cancelled) {
          setDeliverables([]);
        }
      }
    }

    loadDeliverables();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="insight-stack vehicle-brief-stack">
      <div className="hero-insight">
        <span className="insight-kicker">Vehicle Brief</span>
        <strong>{groups.length === 1 ? groups[0][0].commercial_name || groups[0][0].car_family : `${groups.length} matched vehicles`}</strong>
        <p>{query}</p>
      </div>
      {groups.map((rows) => {
        const head = rows[0];
        const milestoneContext = buildCurrentAndUpcomingMilestones(head, deliverables);
        const vehicleDetails = buildVehicleDetails(rows);
        return (
          <section className="vehicle-brief" key={`${head.car_family}-${head.commercial_name}`}>
            <div className="vehicle-hero">
              <div>
                <div className="vehicle-identity">
                  <h3>{head.commercial_name || head.car_family}</h3>
                  <p>{[head.brand, head.car_family].filter(Boolean).join(" / ")}</p>
                </div>
                <div className="chip-row">
                  {head.program ? <span className="data-chip">{head.program}</span> : null}
                  {head.platform ? <span className="data-chip">{head.platform}</span> : null}
                  {head.region_of_sales ? <span className="data-chip">{head.region_of_sales}</span> : null}
                </div>
              </div>
              {renderVehicleImage(head)}
            </div>

            <section className="brief-section">
              <span className="section-kicker">Summary</span>
              <p className="brief-copy">{buildVehicleSummary(rows)}</p>
            </section>

            {milestoneContext.current || milestoneContext.upcoming ? (
              <section className="brief-section">
                <div className="brief-section-header">
                  <span className="section-kicker">Current Milestone</span>
                </div>
                <div className="deliverable-brief dual-milestone-cards">
                  {milestoneContext.current ? (
                    <div className="deliverable-brief-item">
                      <span>Current Milestone: {milestoneContext.current.label}</span>
                      {milestoneContext.current.deliverable ? (
                        <ul className="deliverable-list">
                          {String(milestoneContext.current.deliverable.readiness_objectives || "")
                            .split("\n")
                            .map((item) => item.trim())
                            .filter(Boolean)
                            .map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                        </ul>
                      ) : (
                        <p className="deliverable-subtitle">No milestone-specific deliverables are stored yet for {milestoneContext.current.label}.</p>
                      )}
                      <div className="ownership-block">
                        <span>Ownership</span>
                        <p>{milestoneContext.current.deliverable?.ownership || "Not provided"}</p>
                      </div>
                    </div>
                  ) : null}
                  {milestoneContext.upcoming && milestoneContext.current?.label !== "SOPM" ? (
                    <div className="deliverable-brief-item">
                      <span>Upcoming Milestone: {milestoneContext.upcoming.label}</span>
                      <p className="deliverable-subtitle">During {formatValue(milestoneContext.upcoming.date)}</p>
                      {milestoneContext.upcoming.deliverable ? (
                        <ul className="deliverable-list">
                          {String(milestoneContext.upcoming.deliverable.readiness_objectives || "")
                            .split("\n")
                            .map((item) => item.trim())
                            .filter(Boolean)
                            .map((item) => (
                              <li key={item}>{item}</li>
                            ))}
                        </ul>
                      ) : (
                        <p className="deliverable-subtitle">No milestone-specific deliverables are stored yet for {milestoneContext.upcoming.label}.</p>
                      )}
                      <div className="ownership-block">
                        <span>Ownership</span>
                        <p>{milestoneContext.upcoming.deliverable?.ownership || "Not provided"}</p>
                      </div>
                    </div>
                  ) : null}
                </div>
              </section>
            ) : null}

            <section className="brief-section">
              <div className="brief-section-header">
                <span className="section-kicker">Milestones</span>
              </div>
              {renderMilestoneTimeline(head, milestoneContext.upcoming?.label)}
            </section>

            <section className="brief-section">
              <div className="brief-section-header">
                <span className="section-kicker">Vehicle Details</span>
              </div>
              <div className="vehicle-detail-grid">
                {vehicleDetails.map((item) => (
                  <div className="vehicle-detail-item" key={item.label}>
                    <span>{item.label}</span>
                    <strong>{item.value}</strong>
                  </div>
                ))}
              </div>
            </section>

            {rows.length > 1 ? (
              <section className="brief-section">
                <div className="brief-section-header">
                  <span className="section-kicker">Launch Footprint</span>
                </div>
                <div className="launch-row-list">
                  {rows.map((row, index) => (
                    <div className="launch-row-card" key={`${head.car_family}-${row.region_of_sales ?? ""}-${index}`}>
                      <div>
                        <strong>{formatValue(resolveRelevantLaunch([row])?.value || row.sopm)}</strong>
                        <p>{[row.region_of_sales, row.initial_prod_zone].filter(Boolean).join(" / ") || "Region not provided"}</p>
                      </div>
                      <div className="chip-row">
                        {row.tcu_details ? <span className="data-chip">{row.tcu_details}</span> : null}
                        {row.infotainment_details ? <span className="data-chip">{row.infotainment_details}</span> : null}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}

function renderLaunchCards(answer, options = {}) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No rows matched the current deterministic plan.</p>;
  }

  return (
    <div className="insight-stack">
      {options.compact ? null : null}
      <div className="card-grid">
        {answer.map((row, index) => (
          <article className="launch-card" key={`${row.car_family ?? "row"}-${index}`}>
            <div className="launch-card-top">
              <strong>{row.commercial_name || row.car_family || "Launch Row"}</strong>
              <span>{formatValue(row.sopm ?? row.launch_date)}</span>
            </div>
            <p>{[row.brand, row.car_family, row.platform].filter(Boolean).join(" / ")}</p>
            <div className="chip-row">
              {row.region_of_sales ? <span className="data-chip">{row.region_of_sales}</span> : null}
              {row.initial_prod_zone ? <span className="data-chip">{row.initial_prod_zone}</span> : null}
              {row.launch_stage ? <span className="data-chip">{row.launch_stage}</span> : null}
              {row.ota ? <span className="data-chip">{row.ota}</span> : null}
            </div>
            {renderMilestoneStrip(row)}
            <dl className="card-facts">
              {row.tcu_details ? (
                <>
                  <dt>TCU</dt>
                  <dd>{row.tcu_details}</dd>
                </>
              ) : null}
              {row.infotainment_details ? (
                <>
                  <dt>Infotainment</dt>
                  <dd>{row.infotainment_details}</dd>
                </>
              ) : null}
            </dl>
          </article>
        ))}
      </div>
    </div>
  );
}

function renderRegionalFootprint(answer, response) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No regional footprint rows matched the current plan.</p>;
  }

  if ("value" in answer[0]) {
    const total = answer.reduce((sum, row) => sum + Number(row.value || 0), 0);
    const sorted = [...answer].sort((left, right) => Number(right.value || 0) - Number(left.value || 0));
    return (
      <div className="insight-stack">
        <div className="hero-insight">
          <span className="insight-kicker">Regional Footprint</span>
          <strong>{sorted[0] ? `${formatValue(sorted[0].region_of_sales || sorted[0].region_value)} leads` : "Regional view"}</strong>
          <p>{formatValue(total)} total across the current grouping for: {response.query}</p>
        </div>
        <div className="footprint-grid">
          {sorted.map((row, index) => {
            const label = row.region_of_sales || row.region_value || row.initial_prod_zone || `Group ${index + 1}`;
            const share = total > 0 ? `${Math.round((Number(row.value || 0) / total) * 100)}%` : "0%";
            return (
              <article className="footprint-card" key={`${label}-${index}`}>
                <span>{formatValue(label)}</span>
                <strong>{formatValue(row.value)}</strong>
                <p>{share} of the current result</p>
              </article>
            );
          })}
        </div>
      </div>
    );
  }

  const byRegion = [...answer.reduce((map, row) => {
    const label = row.region_of_sales || row.initial_prod_zone || "Unassigned";
    map.set(label, (map.get(label) || 0) + 1);
    return map;
  }, new Map()).entries()];

  return (
    <div className="insight-stack">
      <div className="hero-insight">
        <span className="insight-kicker">Regional Footprint</span>
        <strong>{byRegion.length} regional buckets</strong>
        <p>{response.query}</p>
      </div>
      <div className="footprint-grid">
        {byRegion.map(([label, count]) => (
          <article className="footprint-card" key={label}>
            <span>{label}</span>
            <strong>{count}</strong>
            <p>matching launch rows</p>
          </article>
        ))}
      </div>
      {renderLaunchWindowCardGrid(answer)}
    </div>
  );
}

function renderComponentMatch(answer, response, options = {}) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No component-matching rows were found.</p>;
  }

  const components = extractMatchedComponents(response?.plan?.filters);
  const vehicleRows = canRenderSharedVehicleCards(answer);
  const matchedVehicles = groupRowsByEntity(answer).length;

  return (
    <div className="insight-stack">
      {options.compact ? null : (
        <div className="hero-insight">
          <span className="insight-kicker">Component Match</span>
          <strong>{matchedVehicles} matched vehicle profiles</strong>
          <p>{response.query}</p>
          <div className="chip-row">
            {components.map((item) => (
              <span className="data-chip" key={`${item.field}-${item.value}`}>
                {toTitleCase(item.field)}: {item.value}
              </span>
            ))}
          </div>
        </div>
      )}
      {vehicleRows
        ? options.compact
          ? renderComponentMatchCardGrid(answer.slice(0, 6))
          : renderComponentMatchCardGrid(answer)
        : renderTable(answer)}
    </div>
  );
}

function renderCompareView(answer, response) {
  if (!Array.isArray(answer) || answer.length === 0) {
    return <p className="empty-state">No comparable vehicle profiles were found.</p>;
  }

  const groups = groupRowsByEntity(answer).slice(0, 4);
  return (
    <div className="insight-stack">
      <div className="hero-insight">
        <span className="insight-kicker">Compare</span>
        <strong>{groups.length} vehicles side by side</strong>
        <p>{response.query}</p>
      </div>
      <div className="compare-grid">
        {groups.map((rows) => {
          const head = rows[0];
          return (
            <section className="compare-card" key={`${head.car_family}-${head.commercial_name}`}>
              <h3>{head.commercial_name || head.car_family}</h3>
              <p>{[head.brand, head.car_family, head.platform].filter(Boolean).join(" / ")}</p>
              {renderMilestoneStrip(head)}
              <div className="compare-facts">
                <div>
                  <span>Regions</span>
                  <strong>{rows.map((row) => row.region_of_sales).filter(Boolean).join(", ") || "Not provided"}</strong>
                </div>
                <div>
                  <span>TCU</span>
                  <strong>{head.tcu_details || "Not provided"}</strong>
                </div>
                <div>
                  <span>Infotainment</span>
                  <strong>{head.infotainment_details || "Not provided"}</strong>
                </div>
                <div>
                  <span>OTA</span>
                  <strong>{head.ota || "Not provided"}</strong>
                </div>
              </div>
            </section>
          );
        })}
      </div>
    </div>
  );
}

function inferViewMode(response) {
  const answer = response?.answer;
  const query = response?.query?.toLowerCase() ?? "";
  const filters = response?.plan?.filters ?? [];
  const isVehicleIntent =
    query.includes("tell me about") ||
    query.includes("details for") ||
    hasAnyFilter(filters, ["car_family", "commercial_name", "car_family_code"]);

  if (!Array.isArray(answer)) {
    return { id: "structured_table", label: "Structured Table", description: "Default deterministic row view." };
  }
  if (queryStartsWith(query, ["when "]) && query.includes("launch")) {
    return { id: "launch_brief", label: "Launch Brief", description: "Summarizes launch timing by vehicle, stage, and region." };
  }
  if (response?.plan?.data_view === "launch_event" && response?.answer_type === "list") {
    return { id: "launch_window", label: "Launch Window", description: "Groups launch events while merging RoS-only splits with identical timing and configuration." };
  }
  if (isVehicleIntent && answer.length > 0 && answer.length <= 24) {
    return { id: "vehicle_profile", label: "Vehicle Brief", description: "Summarizes the selected vehicle with lifecycle and readiness context." };
  }
  if (answer.some((row) => Object.keys(row).some((key) => key.startsWith("milestone_")))) {
    return { id: "milestone_plan", label: "Milestone Plan", description: "Shows the backward-calculated milestone cadence from the selected anchor date." };
  }
  if (query.includes("compare") || query.includes(" vs ")) {
    return { id: "compare", label: "Compare", description: "Puts a few matched vehicle profiles side by side." };
  }
  if (answer.some((row) => "event_count" in row && "stage_mix" in row)) {
    return { id: "overlap_load", label: "Overlap Load", description: "Highlights months where multiple launch stages pile up together." };
  }
  if (queryStartsWith(query, ["does ", "is ", "are ", "can "])) {
    return { id: "evidence_check", label: "Evidence Check", description: "Answers a yes or no style question with the exact supporting rows." };
  }
  if (queryStartsWith(query, ["when "]) || query.includes(" launch?") || query.includes(" launching?")) {
    return { id: "launch_timeline", label: "Launch Timeline", description: "Puts the matching launches on a readable timing track." };
  }
  if (hasAnyFilter(filters, ["tcu_details", "infotainment_details", "ota", "eea", "architecture"])) {
    return { id: "component_match", label: "Component Match", description: "Focuses on the matched stack, readiness, or architecture combination." };
  }
  if (response?.answer_type === "distribution" || hasAnyFilter(filters, ["region_of_sales", "initial_prod_zone", "project_responsible_region"])) {
    return { id: "regional_footprint", label: "Regional Footprint", description: "Shows how the current result spreads across regions or production zones." };
  }
  if (answer.length <= 12) {
    return { id: "launch_cards", label: "Launch Cards", description: "Compact card view for a focused set of launch rows." };
  }
  return { id: "structured_table", label: "Structured Table", description: "Full row-level view for broader result sets." };
}

function renderViewMode(mode, response) {
  const answer = response?.answer;
  switch (mode.id) {
    case "milestone_plan":
      return renderMilestonePlan(answer, response);
    case "compare":
      return renderCompareView(answer, response);
    case "overlap_load":
      return renderOverlapCards(answer);
    case "evidence_check":
      return renderBinaryResponse(answer, response);
    case "launch_timeline":
      return renderLaunchTimeline(answer, response);
    case "launch_brief":
      return renderLaunchBrief(answer, response);
    case "launch_window":
      return renderLaunchWindow(answer, response);
    case "vehicle_profile":
      return renderEntitySpotlight(answer, response);
    case "component_match":
      return renderComponentMatch(answer, response);
    case "regional_footprint":
      return renderRegionalFootprint(answer, response);
    case "launch_cards":
      return renderLaunchCards(answer);
    case "structured_table":
    default:
      return renderTable(answer);
  }
}

function resolvePlannerStatus(response) {
  const diagnostics = response?.plan?.planner_diagnostics;
  const notes = diagnostics?.decision_notes ?? [];
  const llmSuggestion = diagnostics?.llm_suggestion;

  if (notes.some((note) => note.toLowerCase().includes("planner mode requested by ui: hybrid")) && notes.some((note) => note.toLowerCase().includes("no llm provider was available"))) {
    return { label: "Hybrid Fallback", tone: "fallback" };
  }
  if (llmSuggestion && llmSuggestion.accepted_overrides?.length) {
    return { label: "Hybrid", tone: "hybrid" };
  }
  if (notes.some((note) => note.toLowerCase().includes("planner mode requested by ui: hybrid"))) {
    return { label: "Hybrid", tone: "hybrid" };
  }
  if (notes.some((note) => note.toLowerCase().includes("used full llm planner output"))) {
    return { label: "LLM", tone: "hybrid" };
  }
  return { label: "Heuristic", tone: "heuristic" };
}

export function AnswerCard({ response, loading, onExport, exporting = false }) {
  let body = <p className="empty-state">Results will appear here once a question is submitted.</p>;
  let mode = null;
  const plannerStatus = resolvePlannerStatus(response);

  if (loading) {
    body = <p className="empty-state">Preparing the response...</p>;
  } else if (response?.status === "unsupported") {
    body = (
      <div className="unsupported-state">
        <p>This question cannot be completed with the currently available source data.</p>
        <ul className="detail-list">
          {(response.plan?.unsupported_reasons ?? []).map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>
    );
  } else if (response?.status === "clarification_needed") {
    body = <p className="empty-state">A clarification is needed before the answer can be finalized.</p>;
  } else if (response?.status === "ok") {
    if (response.answer_type === "count") {
      body = renderCount(response.answer);
      mode = { id: "count", label: "Metric Readout", description: "Single-value deterministic result." };
    } else {
      mode = inferViewMode(response);
      body = renderViewMode(mode, response);
    }
  }

  return (
    <section className="panel answer-panel">
      <div className="panel-header">
        <div>
          <h2>Answer Workspace</h2>
          <p>{response?.query || "Portfolio answers, milestone briefs, and launch views appear here."}</p>
        </div>
        <div className="panel-header-actions">
          {response?.query ? (
            <span className={`planner-status-badge planner-status-${plannerStatus.tone}`}>{plannerStatus.label}</span>
          ) : null}
          {response?.status === "ok" && Array.isArray(response?.answer) && response.answer.length > 0 ? (
            <button type="button" className="ghost-button export-button" onClick={onExport} disabled={exporting}>
              {exporting ? "Exporting..." : "Export Excel"}
            </button>
          ) : null}
          <span className="badge">{mode?.label || response?.answer_type || "idle"}</span>
        </div>
      </div>
      {body}
    </section>
  );
}
