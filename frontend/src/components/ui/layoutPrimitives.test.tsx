import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { Container } from "./Container";
import { SectionHeader } from "./SectionHeader";

describe("Container", () => {
  it("caps content at the 1440px token with the 16 / 32 / 64px gutters", () => {
    const { container } = render(<Container>Body</Container>);
    expect(container.firstElementChild).toHaveClass("max-w-content", "mx-auto", "px-margin-mobile", "tablet:px-8", "desktop:px-margin-desktop");
  });

  it("can render as another element and keeps extra classes", () => {
    const { container } = render(
      <Container as="section" className="py-8">
        Body
      </Container>
    );
    expect(container.firstElementChild?.tagName).toBe("SECTION");
    expect(container.firstElementChild).toHaveClass("py-8");
  });
});

describe("SectionHeader", () => {
  it("always renders a real h2 with the id the section is labelled by", () => {
    render(<SectionHeader headingId="x-heading" title="Featured" description="Real copy" eyebrow="Eyebrow" />);
    const heading = screen.getByRole("heading", { level: 2, name: "Featured" });
    expect(heading).toHaveAttribute("id", "x-heading");
    expect(screen.getByText("Real copy")).toBeInTheDocument();
  });

  it("split alignment renders the supplied action beside the heading", () => {
    render(<SectionHeader headingId="y" title="Featured" align="split" action={<button type="button">View all</button>} />);
    expect(screen.getByRole("button", { name: "View all" })).toBeInTheDocument();
  });
});
