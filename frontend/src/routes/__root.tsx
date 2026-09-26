import { type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Outlet, createRootRouteWithContext, HeadContent, Scripts } from "@tanstack/react-router";

import { Layout } from "@/components/Layout";
import { Toaster } from "@/components/ui/sonner";
import { THEME_STORAGE_KEY } from "@/store/themeStore";
// URL import (not a side-effect import): this registers styles.css as a build
// asset whose emitted href we hand to TanStack Start's head links below. A bare
// `import '@/styles.css'` only injects styles in Vite dev; in the production
// SSR build the stylesheet <link> must be declared via head() + <HeadContent/>.
import appCss from "@/styles.css?url";

const ANTI_FOUC_SCRIPT = `(function() {
  try {
    var key = '${THEME_STORAGE_KEY}';
    var stored = localStorage.getItem(key);
    var theme = 'dark';
    if (stored) {
      try {
        var parsed = JSON.parse(stored);
        theme = parsed.state?.theme || parsed.theme || stored;
      } catch (e) {
        theme = stored;
      }
    }
    var resolved = theme;
    if (theme === 'system' || !theme) {
      resolved = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }
    var root = document.documentElement;
    if (resolved === 'dark') {
      root.classList.add('dark');
      root.classList.remove('light');
      root.style.colorScheme = 'dark';
    } else {
      root.classList.add('light');
      root.classList.remove('dark');
      root.style.colorScheme = 'light';
    }
    root.setAttribute('data-theme', resolved);
  } catch (e) {}
})();`;

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
    ],
    links: [{ rel: "stylesheet", href: appCss }],
  }),
  shellComponent: RootShell,
  component: RootComponent,
});

// The HTML document shell. TanStack Start renders this for the root route; it is
// where <HeadContent/> emits the collected <head> tags (including the stylesheet
// link above) and <Scripts/> emits the client entry for hydration.
function RootShell({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <HeadContent />
        <script dangerouslySetInnerHTML={{ __html: ANTI_FOUC_SCRIPT }} />
      </head>
      <body className="bg-background text-foreground transition-colors duration-200">
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  return (
    <QueryClientProvider client={queryClient}>
      <Layout>
        <Outlet />
      </Layout>
      {/* App-wide toast surface. Mounted once at the root. */}
      <Toaster />
    </QueryClientProvider>
  );
}
