import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { cn } from "@/lib/utils";

import { Avatar, AvatarFallback } from "./avatar";
import { Badge } from "./badge";
import { Button, buttonVariants } from "./button";
import { Card, CardContent, CardHeader, CardTitle } from "./card";
import { Input } from "./input";
import { ScrollArea } from "./scroll-area";
import { Separator } from "./separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./tabs";

describe("cn", () => {
  it("lets the later Tailwind class win", () => {
    expect(cn("px-2", "px-6")).toBe("px-6");
    expect(cn("a", false && "b", "c")).toBe("a c");
  });
});

describe("Button", () => {
  it("is a real button, at least 56px, with a visible focus ring", () => {
    const html = renderToStaticMarkup(<Button>घेतलं</Button>);
    expect(html).toContain("<button");
    expect(html).toContain('type="button"');
    expect(html).toContain("min-h-touch");
    expect(html).toContain("min-w-touch");
    expect(html).toContain("focus-visible:ring-4");
    expect(html).toContain("घेतलं");
  });
  it("uses amber (primary) by default and red only for the emergency variant", () => {
    expect(buttonVariants()).toContain("bg-primary");
    expect(buttonVariants()).not.toContain("emergency");
    expect(buttonVariants({ variant: "emergency" })).toContain("bg-emergency");
    for (const v of ["default", "secondary", "outline", "ghost"] as const) {
      expect(buttonVariants({ variant: v })).not.toContain("emergency");
    }
  });
  it("large and icon sizes keep the touch target", () => {
    expect(buttonVariants({ size: "lg" })).toContain("min-h-[72px]");
    expect(buttonVariants({ size: "icon" })).toContain("size-touch");
  });
  it("can render as its child (asChild)", () => {
    const html = renderToStaticMarkup(
      <Button asChild>
        <a href="/x">go</a>
      </Button>,
    );
    expect(html).toContain("<a ");
    expect(html).not.toContain("<button");
  });
});

describe("Card", () => {
  it("is cream with the cream border and a 28px heading", () => {
    const html = renderToStaticMarkup(
      <Card>
        <CardHeader>
          <CardTitle>औषधं</CardTitle>
        </CardHeader>
        <CardContent>x</CardContent>
      </Card>,
    );
    expect(html).toContain("bg-card");
    expect(html).toContain("border-border");
    expect(html).toContain("text-[28px]");
    expect(html).toContain("<h2");
  });
});

describe("Input", () => {
  it("is 56px tall with a visible border and 20px text", () => {
    const html = renderToStaticMarkup(<Input aria-label="x" />);
    expect(html).toContain("min-h-touch");
    expect(html).toContain("border-input");
    expect(html).toContain("text-xl");
  });
});

describe("Badge, Separator, Avatar", () => {
  it("badge text is never below 20px", () => {
    expect(renderToStaticMarkup(<Badge>ok</Badge>)).toContain("text-xl");
  });
  it("a decorative separator is hidden from screen readers", () => {
    expect(renderToStaticMarkup(<Separator />)).toContain('role="none"');
  });
  it("avatar shows its fallback when there is no image", () => {
    const html = renderToStaticMarkup(
      <Avatar>
        <AvatarFallback>आ</AvatarFallback>
      </Avatar>,
    );
    expect(html).toContain("आ");
  });
});

describe("Tabs and ScrollArea", () => {
  it("tabs expose tablist / tab roles and 56px triggers", () => {
    const html = renderToStaticMarkup(
      <Tabs defaultValue="a">
        <TabsList>
          <TabsTrigger value="a">One</TabsTrigger>
          <TabsTrigger value="b">Two</TabsTrigger>
        </TabsList>
        <TabsContent value="a">first</TabsContent>
      </Tabs>,
    );
    expect(html).toContain('role="tablist"');
    expect(html).toContain('role="tab"');
    expect(html).toContain("min-h-touch");
    expect(html).toContain("first");
  });
  it("scroll area renders its content", () => {
    expect(renderToStaticMarkup(<ScrollArea className="h-10">hello</ScrollArea>)).toContain("hello");
  });
});
