import {
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import {
  Outlet,
  createRootRouteWithContext,
  useRouter,
  HeadContent,
  Scripts,
  useRouterState,
} from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";
import { Toaster } from "sonner";
import { AnimatePresence, motion } from "framer-motion";

import appCss from "../styles.css?url";
import { reportLovableError } from "../lib/lovable-error-reporting";
import { Header } from "@/components/navbar/Header";
import { Sidebar } from "@/components/navbar/Sidebar";
import { Footer } from "@/components/navbar/Footer";
import { ScrollToTop } from "@/components/common/ScrollToTop";

function NotFoundComponent() {
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col items-center justify-center px-6 text-center">
      <h1 className="text-7xl font-black text-gradient-rabbit">404</h1>
      <h2 className="mt-4 text-xl font-semibold">Page not found</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <a
        href="/"
        className="mt-6 inline-flex items-center rounded-full gradient-rabbit px-5 py-2 text-sm font-semibold text-white"
      >
        Back to Home
      </a>
    </div>
  );
}

function ErrorComponent({ error, reset }: { error: Error; reset: () => void }) {
  const router = useRouter();
  useEffect(() => {
    reportLovableError(error, { boundary: "tanstack_root_error_component" });
  }, [error]);
  return (
    <div className="mx-auto flex min-h-[70vh] max-w-md flex-col items-center justify-center px-6 text-center">
      <h1 className="text-xl font-semibold">This page didn't load</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Something went wrong on our end.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        <button
          onClick={() => {
            router.invalidate();
            reset();
          }}
          className="rounded-full gradient-rabbit px-5 py-2 text-sm font-semibold text-white"
        >
          Try again
        </button>
        <a
          href="/"
          className="rounded-full border border-white/10 bg-white/5 px-5 py-2 text-sm"
        >
          Go home
        </a>
      </div>
    </div>
  );
}

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()(
  {
    head: () => ({
      meta: [
        { charSet: "utf-8" },
        { name: "viewport", content: "width=device-width, initial-scale=1" },
        {
          title:
            "Rabbit — AI Movie Recommendations, Trending Movies & Web Series",
        },
        {
          name: "description",
          content:
            "Rabbit uses Behavioral Intelligence to recommend movies and web series across Netflix, Prime Video, Disney+, and JioHotstar.",
        },
        { name: "author", content: "Rabbit" },
        {
          property: "og:title",
          content: "Rabbit — AI Movie Recommendations",
        },
        {
          property: "og:description",
          content:
            "Personalized movie & series recommendations powered by Behavioral Intelligence.",
        },
        { property: "og:type", content: "website" },
        { name: "twitter:card", content: "summary_large_image" },
      ],
      links: [
        { rel: "stylesheet", href: appCss },
        { rel: "icon", href: "/favicon.ico", type: "image/x-icon" },
      ],
    }),
    shellComponent: RootShell,
    component: RootComponent,
    notFoundComponent: NotFoundComponent,
    errorComponent: ErrorComponent,
  },
);

function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <HeadContent />
      </head>
      <body className="dark bg-background text-foreground">
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  return (
    <QueryClientProvider client={queryClient}>
      <div className="relative flex min-h-screen flex-col">
        <Header />
        <Sidebar />
        <main className="flex-1">
          <AnimatePresence mode="wait">
            <motion.div
              key={pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
            >
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
        <Footer />
        <ScrollToTop />
        <Toaster theme="dark" position="top-center" richColors />
      </div>
    </QueryClientProvider>
  );
}
