export type CsvRow = Record<string, string>;

export type TaskSummary = {
  taskId: string;
  trials: number;
  outcomes: Record<string, number>;
  outcomeTotal: number;
  dominantEngineerLabel: string;
  dominantGlobalPattern: string;
};

export type ReportSummary = {
  trials: number;
  tasks: number;
  solved: number;
  traceVerified: number;
  silentFailure: number;
  validationUnknown: number;
  unsolved: number;
  criticFalseAccept: number;
  compilerCalledRows: number;
  kernelAccepted: number;
  kernelRejected: number;
  kernelUnknown: number;
};

export function parseCsv(text: string): CsvRow[] {
  const table: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"' && inQuotes && next === '"') {
      cell += '"';
      i += 1;
      continue;
    }
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (char === "," && !inQuotes) {
      row.push(cell);
      cell = "";
      continue;
    }
    if ((char === "\n" || char === "\r") && !inQuotes) {
      if (char === "\r" && next === "\n") {
        i += 1;
      }
      row.push(cell);
      if (row.some((value) => value.length > 0)) {
        table.push(row);
      }
      row = [];
      cell = "";
      continue;
    }
    cell += char;
  }

  if (cell.length > 0 || row.length > 0) {
    row.push(cell);
    if (row.some((value) => value.length > 0)) {
      table.push(row);
    }
  }

  const [headers, ...records] = table;
  if (!headers) {
    return [];
  }
  return records.map((record) => {
    const item: CsvRow = {};
    headers.forEach((header, index) => {
      item[header] = record[index] ?? "";
    });
    return item;
  });
}

export function countBy(rows: CsvRow[], field: string): Map<string, number> {
  const counts = new Map<string, number>();
  rows.forEach((row) => {
    const key = row[field] || "none";
    counts.set(key, (counts.get(key) ?? 0) + 1);
  });
  return counts;
}

export function uniqueValues(rows: CsvRow[], field: string): string[] {
  return Array.from(new Set(rows.map((row) => row[field]).filter(Boolean))).sort();
}

export function topLabel(rows: CsvRow[], field: string): string {
  const entries = Array.from(countBy(rows, field).entries()).sort((a, b) => {
    if (b[1] !== a[1]) {
      return b[1] - a[1];
    }
    return a[0].localeCompare(b[0]);
  });
  return entries[0]?.[0] ?? "none";
}

export function summarize(rows: CsvRow[]): ReportSummary {
  const outcomes = countBy(rows, "validator_outcome");
  const critics = countBy(rows, "critic_label");
  const validationStatus = (row: CsvRow): string => {
    if (row.validation_status) {
      return row.validation_status.toLowerCase();
    }
    const legacy = (row.final_proof_compiles || "").toLowerCase();
    if (["true", "accepted", "pass", "passed"].includes(legacy)) {
      return "accepted";
    }
    if (["false", "rejected", "fail", "failed"].includes(legacy)) {
      return "rejected";
    }
    return "not_evaluated";
  };
  const kernelAccepted = rows.filter((row) => validationStatus(row) === "accepted").length;
  const kernelRejected = rows.filter((row) => validationStatus(row) === "rejected").length;
  const hasStrictWorkflowFields = rows.some(
    (row) => row.validation_status && row.submission_accepted,
  );
  const silentFailure = hasStrictWorkflowFields
    ? rows.filter(
        (row) =>
          (row.submission_accepted || "").toLowerCase() === "true" &&
          validationStatus(row) === "rejected",
      ).length
    : outcomes.get("silent_failure") ?? 0;
  return {
    trials: rows.length,
    tasks: uniqueValues(rows, "task_id").length,
    solved: outcomes.get("solved") ?? 0,
    traceVerified: outcomes.get("trace_verified") ?? 0,
    silentFailure,
    validationUnknown: outcomes.get("validation_unknown") ?? 0,
    unsolved: outcomes.get("unsolved") ?? 0,
    criticFalseAccept: critics.get("critic_false_accept") ?? 0,
    compilerCalledRows: rows.filter((row) => Number(row.n_tool_calls || 0) > 0).length,
    kernelAccepted,
    kernelRejected,
    kernelUnknown: rows.length - kernelAccepted - kernelRejected,
  };
}

export function taskSummaries(rows: CsvRow[]): TaskSummary[] {
  return uniqueValues(rows, "task_id").map((taskId) => {
    const taskRows = rows.filter((row) => row.task_id === taskId);
    const outcomes = countBy(taskRows, "validator_outcome");
    const outcomeRecord = Object.fromEntries(outcomes.entries());
    return {
      taskId,
      trials: taskRows.length,
      outcomes: outcomeRecord,
      outcomeTotal: Object.values(outcomeRecord).reduce((sum, count) => sum + count, 0),
      dominantEngineerLabel: topLabel(taskRows, "engineer_failure_label"),
      dominantGlobalPattern: topLabel(taskRows, "global_graph_pattern"),
    };
  });
}
