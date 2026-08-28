import { Link } from "@tanstack/react-router";
import { RabbitLogo } from "./RabbitLogo";

export function Footer() {
  return (
    <footer className="mt-24 border-t border-white/5 bg-background/60">
      <div className="mx-auto grid max-w-7xl gap-10 px-6 py-12 md:grid-cols-4">
        <div>
          <div className="mb-3 flex items-center gap-2">
            <RabbitLogo className="h-8 w-8" />
            <span className="text-lg font-bold">
              <span className="text-gradient-rabbit">Rabbit</span>
            </span>
          </div>
          <p className="text-sm text-muted-foreground">
            Recommendation And Browsing Based on Behavioral Intelligence
            Technology.
          </p>
        </div>

        <FooterCol title="Quick Links">
          <FooterLink to="/">Home</FooterLink>
          <FooterLink to="/search">Search</FooterLink>
          <FooterLink to="/favorites">Favorites</FooterLink>
          <FooterLink to="/history">History</FooterLink>
          <FooterLink to="/profile">Profile</FooterLink>
          <FooterLink to="/settings">Settings</FooterLink>
        </FooterCol>

        <FooterCol title="Company">
          <FooterLink to="/">About Rabbit</FooterLink>
          <FooterLink to="/">Contact</FooterLink>
          <FooterLink to="/">Privacy Policy</FooterLink>
          <FooterLink to="/">Terms of Service</FooterLink>
        </FooterCol>

        <div>
          <h4 className="mb-3 text-sm font-semibold">Newsletter</h4>
          <p className="mb-3 text-xs text-muted-foreground">
            Get weekly AI-picked movie recommendations.
          </p>
          <form
            onSubmit={(e) => e.preventDefault()}
            className="flex overflow-hidden rounded-full border border-white/10 bg-white/5"
          >
            <input
              type="email"
              required
              placeholder="you@example.com"
              className="flex-1 bg-transparent px-4 py-2 text-sm placeholder:text-muted-foreground focus:outline-none"
            />
            <button className="gradient-rabbit px-4 text-sm font-semibold text-white">
              Join
            </button>
          </form>
        </div>
      </div>
      <div className="border-t border-white/5 py-4 text-center text-xs text-muted-foreground">
        © 2026 Rabbit. All Rights Reserved.
      </div>
    </footer>
  );
}

function FooterCol({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h4 className="mb-3 text-sm font-semibold">{title}</h4>
      <ul className="space-y-2 text-sm text-muted-foreground">{children}</ul>
    </div>
  );
}

function FooterLink({
  to,
  children,
}: {
  to: string;
  children: React.ReactNode;
}) {
  return (
    <li>
      <Link to={to} className="hover:text-foreground transition-colors">
        {children}
      </Link>
    </li>
  );
}
