import { Bell, Mic } from "lucide-react";
import { useState } from "react";

import { Orb } from "@/components/Orb";
import { ORB_STATES, type OrbState } from "@/components/orbState";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { orbLabel } from "@/elder/i18n";
import { useLayout } from "@/lib/layout";

/** Developer page (`/?ui=1`): every new base component and every orb state, for phone + laptop checks. Not an app screen. */
export function UiGallery() {
  const layout = useLayout();
  const [orb, setOrb] = useState<OrbState>("listening");
  return (
    <div className="ui-root min-h-screen p-4 md:p-8">
      <header className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="text-[28px] font-semibold">UI foundation (Phase 1)</h1>
        <Badge variant="outline" data-testid="layout">
          {layout}
        </Badge>
      </header>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Orb</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col items-center gap-5">
            <Orb state={orb} label={orbLabel("mr", orb)} size="12rem" />
            <p className="text-xl text-muted-foreground">{orbLabel("mr", orb)}</p>
            <div className="flex flex-wrap justify-center gap-2">
              {ORB_STATES.map((s) => (
                <Button key={s} variant={s === orb ? "default" : "secondary"} onClick={() => setOrb(s)}>
                  {s}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Buttons and fields</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-wrap gap-3">
              <Button>
                <Mic aria-hidden /> Default
              </Button>
              <Button variant="secondary">Secondary</Button>
              <Button variant="outline">Outline</Button>
              <Button variant="ghost">Ghost</Button>
              <Button size="icon" aria-label="Bell">
                <Bell aria-hidden />
              </Button>
              <Button variant="emergency">Emergency only</Button>
            </div>
            <Input placeholder="Type here" aria-label="Sample field" />
            <div className="flex flex-wrap items-center gap-3">
              <Badge>default</Badge>
              <Badge variant="secondary">secondary</Badge>
              <Badge variant="outline">outline</Badge>
              <Avatar>
                <AvatarFallback>आ</AvatarFallback>
              </Avatar>
            </div>
            <Separator />
            <Tabs defaultValue="a">
              <TabsList>
                <TabsTrigger value="a">One</TabsTrigger>
                <TabsTrigger value="b">Two</TabsTrigger>
              </TabsList>
              <TabsContent value="a">First tab</TabsContent>
              <TabsContent value="b">Second tab</TabsContent>
            </Tabs>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Scroll area</CardTitle>
          </CardHeader>
          <CardContent>
            <ScrollArea className="h-40 rounded-lg border border-border bg-background p-3">
              {Array.from({ length: 12 }, (_, i) => (
                <p key={i} className="py-1">
                  Row {i + 1}
                </p>
              ))}
            </ScrollArea>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Dialog and sheet</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            <Dialog>
              <DialogTrigger asChild>
                <Button variant="secondary">Open dialog</Button>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Sample dialog</DialogTitle>
                  <DialogDescription>Esc or the close button dismisses it.</DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <Button>OK</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="secondary">Open sheet</Button>
              </SheetTrigger>
              <SheetContent side="right">
                <SheetHeader>
                  <SheetTitle>Sample sheet</SheetTitle>
                  <SheetDescription>Slides in from the side.</SheetDescription>
                </SheetHeader>
              </SheetContent>
            </Sheet>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
