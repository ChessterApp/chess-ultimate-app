"use client";

import React, { Suspense } from "react";
import dynamic from "next/dynamic";
import { useTranslations } from "next-intl";

const BoardEditor = dynamic(() => import("@/components/editor/BoardEditor"), {
  ssr: false,
  loading: () => <div className="animate-pulse h-80 bg-gray-200 rounded-xl mx-auto max-w-lg" />
});

function EditorContent() {
  const t = useTranslations("editor");
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-[#0f0f0f] text-gray-900 dark:text-gray-200 pt-4 pb-20">
      <h1 className="text-center text-xl font-semibold mb-4 text-gray-700 dark:text-gray-300">
        {t("boardEditor")}
      </h1>
      <BoardEditor />
    </div>
  );
}

export default function EditorPage() {
  const t = useTranslations("editor");
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-gray-50 dark:bg-[#0f0f0f] flex items-center justify-center text-gray-500 dark:text-gray-400">
          {t("loadingEditor")}
        </div>
      }
    >
      <EditorContent />
    </Suspense>
  );
}
