"use client";

import { AlertCircle, Play } from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";
import { toast } from "sonner";

import {
  ApiError,
  createCodeRun,
  createIrRun,
  createTemplateRun,
  getProfile,
  getTemplates,
  validateSourceCode
} from "@/lib/api";
import { problemIRSchema, type ProblemIR, type Profile, type TemplateMetadata } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";

const Editor = dynamic(() => import("@monaco-editor/react").then((mod) => mod.default), {
  ssr: false,
  loading: () => (
    <Skeleton className="h-72 w-full" aria-label="Loading code editor" />
  )
});

const starterCode = `import numpy as np

# Portfolio-style starter
x = np.array([0, 1, 0, 1, 0, 1])
returns = np.array([0.08, 0.11, 0.09, 0.14, 0.10, 0.13])
objective = returns @ x
maximize(objective)
constraint = np.sum(x) == 3
`;

const defaultMathIr: ProblemIR = {
  name: "custom_math_problem",
  description: "Client-built binary optimization problem",
  variables: [
    { name: "x_0", type: "binary" },
    { name: "x_1", type: "binary" }
  ],
  objective: {
    sense: "maximize",
    linear_terms: { x_0: 1, x_1: 2 },
    quadratic_terms: {},
    constant: 0
  },
  constraints: [
    {
      name: "limit",
      linear_terms: { x_0: 1, x_1: 1 },
      quadratic_terms: {},
      type: "<=",
      rhs: 1
    }
  ],
  metadata: { source: "math_form" }
};

type Mode = "template" | "code" | "math";

export function NewRunPanel() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("template");
  const [templates, setTemplates] = useState<TemplateMetadata[] | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState("portfolio");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [code, setCode] = useState(starterCode);
  const [validatedIr, setValidatedIr] = useState<ProblemIR | null>(null);
  const [parseErrors, setParseErrors] = useState<string[]>([]);
  const [mathIrText, setMathIrText] = useState(JSON.stringify(defaultMathIr, null, 2));
  const [mathError, setMathError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  useEffect(() => {
    getTemplates().then(setTemplates).catch(() => setTemplates([]));
    getProfile().then(setProfile).catch(() => setProfile(null));
  }, []);

  const quotaExhausted = profile ? profile.quota_remaining <= 0 : false;
  const candidateIr = useMemo(() => {
    if (mode === "code") return validatedIr;
    if (mode === "math") return parseMathIr(mathIrText).ir;
    return null;
  }, [mode, validatedIr, mathIrText]);
  const qubits = mode === "template"
    ? templates?.find((template) => template.name === selectedTemplate)?.variable_count
    : candidateIr?.variables.length;

  const submit = () => {
    startTransition(async () => {
      try {
        const result =
          mode === "template"
            ? await createTemplateRun(selectedTemplate)
            : mode === "code"
              ? await createCodeRun(code)
              : await createIrRun(requireMathIr(mathIrText));
        router.push(`/runs/${result.run_id}`);
      } catch (error) {
        handleRunError(error);
      }
    });
  };

  const validateCode = () => {
    startTransition(async () => {
      const result = await validateSourceCode(code);
      if (result.ok && result.ir) {
        setValidatedIr(result.ir);
        setParseErrors([]);
        toast.success("Code parsed into IR");
      } else {
        setValidatedIr(null);
        setParseErrors(result.errors.map((error) => formatParseError(error)));
      }
    });
  };

  const mathParsed = parseMathIr(mathIrText);
  const disabledReason = quotaExhausted
    ? "Monthly quota exhausted."
    : mode === "code" && validatedIr === null
      ? "Validate code before running."
      : mode === "math" && mathParsed.ir === null
        ? "Fix math IR validation errors."
        : null;

  return (
    <TooltipProvider>
      <div className="space-y-6">
        <QubitEstimate qubits={qubits} />
        <Tabs value={mode} onValueChange={(value) => setMode(value as Mode)}>
          <TabsList>
            <TabsTrigger value="template">Template</TabsTrigger>
            <TabsTrigger value="code">Code</TabsTrigger>
            <TabsTrigger value="math">Math</TabsTrigger>
          </TabsList>
          <TabsContent value="template">
            <TemplateTab
              templates={templates}
              selected={selectedTemplate}
              onSelect={setSelectedTemplate}
            />
          </TabsContent>
          <TabsContent value="code">
            <CodeTab
              code={code}
              onChange={setCode}
              onValidate={validateCode}
              parseErrors={parseErrors}
              ir={validatedIr}
            />
          </TabsContent>
          <TabsContent value="math">
            <MathTab
              value={mathIrText}
              onChange={(value) => {
                setMathIrText(value);
                setMathError(parseMathIr(value).error);
              }}
              error={mathError ?? mathParsed.error}
            />
          </TabsContent>
        </Tabs>
        <div className="flex justify-end">
          {disabledReason ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <span>
                  <Button disabled>
                    <Play className="h-4 w-4" />
                    Run pipeline
                  </Button>
                </span>
              </TooltipTrigger>
              <TooltipContent>{disabledReason}</TooltipContent>
            </Tooltip>
          ) : (
            <Button onClick={submit} disabled={isPending}>
              <Play className="h-4 w-4" />
              {isPending ? "Starting..." : "Run pipeline"}
            </Button>
          )}
        </div>
      </div>
    </TooltipProvider>
  );
}

function TemplateTab({
  templates,
  selected,
  onSelect
}: {
  templates: TemplateMetadata[] | null;
  selected: string;
  onSelect: (name: string) => void;
}) {
  if (!templates) {
    return <Skeleton className="h-64" />;
  }
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
      <div className="grid gap-3">
        {templates.map((template) => (
          <button
            key={template.name}
            type="button"
            className={`rounded-lg border bg-card p-4 text-left ${selected === template.name ? "ring-2 ring-primary" : ""}`}
            onClick={() => onSelect(template.name)}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="font-semibold">{template.display_name}</h2>
                <p className="mt-1 text-sm text-muted-foreground">{template.description}</p>
              </div>
              <Badge variant={template.difficulty === "easy" ? "success" : "secondary"}>{template.difficulty}</Badge>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              {template.variable_count} variables · {template.constraint_count} constraints
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {template.domain_tags.map((tag) => <Badge key={tag} variant="outline">{tag}</Badge>)}
            </div>
          </button>
        ))}
      </div>
      <Preview title="Selected template" data={{ template_name: selected, input_source: "template" }} />
    </div>
  );
}

function CodeTab({
  code,
  onChange,
  onValidate,
  parseErrors,
  ir
}: {
  code: string;
  onChange: (value: string) => void;
  onValidate: () => void;
  parseErrors: string[];
  ir: ProblemIR | null;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
      <Card>
        <CardHeader>
          <CardTitle>NumPy source</CardTitle>
          <CardDescription>Validate before committing a full run.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="overflow-hidden rounded-md border">
            <Editor
              height="360px"
              defaultLanguage="python"
              value={code}
              onChange={(value) => onChange(value ?? "")}
              options={{ minimap: { enabled: false }, fontSize: 13 }}
            />
          </div>
          <Button type="button" variant="outline" onClick={onValidate}>Validate</Button>
          {parseErrors.length ? (
            <div className="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
              {parseErrors.map((error) => <p key={error}>{error}</p>)}
            </div>
          ) : null}
        </CardContent>
      </Card>
      <Preview title="Extracted IR" data={ir ?? { status: "Validate code to preview IR" }} />
    </div>
  );
}

function MathTab({ value, onChange, error }: { value: string; onChange: (value: string) => void; error: string | null }) {
  return (
    <div className="grid gap-4 lg:grid-cols-[0.9fr_1.1fr]">
      <Card>
        <CardHeader>
          <CardTitle>Math builder</CardTitle>
          <CardDescription>Edit this structured IR directly for now.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Label htmlFor="math-ir">ProblemIR JSON</Label>
          <textarea
            id="math-ir"
            className="min-h-80 w-full rounded-md border bg-background p-3 font-mono text-sm"
            value={value}
            onChange={(event) => onChange(event.target.value)}
          />
          {error ? <p className="text-sm text-destructive">{error}</p> : null}
        </CardContent>
      </Card>
      <Preview title="Math IR preview" data={parseMathIr(value).ir ?? { error }} />
    </div>
  );
}

function Preview({ title, data }: { title: string; data: unknown }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <pre className="max-h-[28rem] overflow-auto rounded-md bg-muted p-3 text-xs">
          {JSON.stringify(data, null, 2)}
        </pre>
      </CardContent>
    </Card>
  );
}

function QubitEstimate({ qubits }: { qubits: number | undefined }) {
  if (qubits === undefined) return null;
  const warning = qubits >= 18;
  return (
    <div className={`flex items-center gap-2 rounded-md border p-3 text-sm ${warning ? "border-warning/50 text-warning" : "text-muted-foreground"}`}>
      <AlertCircle className="h-4 w-4" />
      Estimated qubits: {qubits}. Free tier cap is 20.
    </div>
  );
}

function parseMathIr(value: string): { ir: ProblemIR | null; error: string | null } {
  try {
    return { ir: problemIRSchema.parse(JSON.parse(value)), error: null };
  } catch (error) {
    return { ir: null, error: error instanceof Error ? error.message : "Invalid ProblemIR" };
  }
}

function requireMathIr(value: string): ProblemIR {
  const parsed = parseMathIr(value);
  if (!parsed.ir) throw new Error(parsed.error ?? "Invalid ProblemIR");
  return parsed.ir;
}

function formatParseError(error: { message: string; line?: number | null; column?: number | null }) {
  const location = error.line ? `Line ${error.line}${error.column ? `:${error.column}` : ""}: ` : "";
  return `${location}${error.message}`;
}

function handleRunError(error: unknown) {
  if (error instanceof ApiError) {
    if (error.status === 429) {
      toast.error("Quota or rate limit reached", {
        description: error.retryAfter ? `Retry after ${error.retryAfter}s.` : "Try again later."
      });
      return;
    }
    if (error.status === 503) {
      toast.error("System busy, retry in 30s");
      return;
    }
  }
  toast.error(error instanceof Error ? error.message : "Could not start run");
}
