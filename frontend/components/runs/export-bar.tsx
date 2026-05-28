"use client";

import { Check, Copy, Download, Loader2, Share2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from "@/components/ui/card";
import {
  ApiError,
  downloadExportFile,
  fetchExportPdfPayload,
  toggleShare,
  triggerBrowserDownload
} from "@/lib/api";
import { deriveExportControlsState, shareUrlFor } from "@/lib/export-state";
import { buildRunPdf } from "@/lib/pdf-export";
import type { Run } from "@/lib/types";

type Props = {
  run: Run;
  onSharedChange?: (shared: boolean) => void;
};

type BusyKind = "notebook" | "script" | "pdf" | "share" | "copy" | null;

export function ExportBar({ run, onSharedChange }: Props) {
  const initial = deriveExportControlsState(run);
  const [shared, setShared] = useState(initial.shared);
  const [busy, setBusy] = useState<BusyKind>(null);
  const [justCopied, setJustCopied] = useState(false);

  useEffect(() => {
    setShared(initial.shared);
  }, [initial.shared]);

  if (!initial.visible) return null;

  const handleDownload = async (format: "notebook" | "script") => {
    setBusy(format);
    try {
      const { blob, filename } = await downloadExportFile(run.id, format);
      triggerBrowserDownload(blob, filename);
      toast.success(`Downloaded ${filename}`);
    } catch (err) {
      reportError(err, `Could not export ${format}`);
    } finally {
      setBusy(null);
    }
  };

  const handlePdfDownload = async () => {
    setBusy("pdf");
    try {
      const payload = await fetchExportPdfPayload(run.id);
      const doc = buildRunPdf(payload.run);
      const filename = `qsim_${(payload.run.template ?? "run").replace(/[^a-z0-9-_]/gi, "-")}_${
        payload.run.id.slice(0, 8)
      }.pdf`;
      doc.save(filename);
      toast.success(`Downloaded ${filename}`);
    } catch (err) {
      reportError(err, "Could not export PDF");
    } finally {
      setBusy(null);
    }
  };

  const handleShareToggleAndCopy = async () => {
    setBusy("share");
    try {
      const next = !shared;
      const response = await toggleShare(run.id, next);
      setShared(response.shared);
      onSharedChange?.(response.shared);
      if (response.shared) {
        const url = shareUrlFor(run.id);
        try {
          await navigator.clipboard.writeText(url);
          setJustCopied(true);
          window.setTimeout(() => setJustCopied(false), 2400);
          toast.success("Link copied to clipboard", { description: url });
        } catch {
          toast.success("Sharing enabled", {
            description: "Copy the URL from the browser bar."
          });
        }
      } else {
        toast("Sharing disabled", {
          description: "The public link no longer works."
        });
      }
    } catch (err) {
      reportError(err, "Could not update share state");
    } finally {
      setBusy(null);
    }
  };

  const handleCopy = async () => {
    if (!shared) {
      await handleShareToggleAndCopy();
      return;
    }
    setBusy("copy");
    try {
      const url = shareUrlFor(run.id);
      await navigator.clipboard.writeText(url);
      setJustCopied(true);
      window.setTimeout(() => setJustCopied(false), 2400);
      toast.success("Link copied to clipboard", { description: url });
    } catch {
      toast.error("Could not access the clipboard.");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Card data-testid="export-bar">
      <CardHeader>
        <CardTitle>Export &amp; share</CardTitle>
        <CardDescription>
          Reproducible artefacts for sharing with colleagues, leadership, or just yourself.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={busy !== null}
            onClick={() => void handleDownload("notebook")}
          >
            {busy === "notebook" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            Qiskit Notebook (.ipynb)
          </Button>
          <Button
            variant="outline"
            disabled={busy !== null}
            onClick={() => void handleDownload("script")}
          >
            {busy === "script" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            Python Script (.py)
          </Button>
          <Button
            variant="outline"
            disabled={busy !== null}
            onClick={() => void handlePdfDownload()}
          >
            {busy === "pdf" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Download className="h-4 w-4" />
            )}
            PDF Report
          </Button>
          <Button
            variant={shared ? "default" : "secondary"}
            disabled={busy !== null}
            onClick={() => void handleCopy()}
            data-testid="share-toggle"
            aria-pressed={shared}
          >
            {busy === "share" || busy === "copy" ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : justCopied ? (
              <Check className="h-4 w-4" />
            ) : shared ? (
              <Copy className="h-4 w-4" />
            ) : (
              <Share2 className="h-4 w-4" />
            )}
            {shared ? (justCopied ? "Link copied" : "Copy shareable link") : "Enable shareable link"}
          </Button>
          {shared ? (
            <Button
              variant="ghost"
              size="sm"
              disabled={busy !== null}
              onClick={() => void handleShareToggleAndCopy()}
              data-testid="share-disable"
            >
              Disable link
            </Button>
          ) : null}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Shared links are read-only and never include your email or other runs.
        </p>
      </CardContent>
    </Card>
  );
}

function reportError(err: unknown, fallback: string) {
  if (err instanceof ApiError) {
    toast.error(`${fallback} (${err.status})`, {
      description: typeof err.detail === "string" ? err.detail : undefined
    });
    return;
  }
  if (err instanceof Error) {
    toast.error(fallback, { description: err.message });
    return;
  }
  toast.error(fallback);
}
