import { cn } from "@skillsignal/ui/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";

const badgeVariants = cva(
	"inline-flex items-center justify-center rounded-full border px-2.5 py-0.5 text-xs font-semibold w-fit whitespace-nowrap shrink-0 transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
	{
		variants: {
			variant: {
				default:
					"border-transparent bg-primary text-primary-foreground hover:bg-primary/80",
				secondary:
					"border-transparent bg-secondary text-secondary-foreground hover:bg-secondary/80",
				destructive:
					"border-transparent bg-destructive text-destructive-foreground hover:bg-destructive/80",
				outline: "text-foreground",
				success:
					"border-emerald-500/20 bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
				warning:
					"border-amber-500/20 bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
				info: "border-blue-500/20 bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300",
			},
		},
		defaultVariants: {
			variant: "default",
		},
	},
);

function Badge({
	className,
	variant,
	...props
}: React.ComponentProps<"div"> & VariantProps<typeof badgeVariants>) {
	return (
		<div className={cn(badgeVariants({ variant }), className)} {...props} />
	);
}

export { Badge, badgeVariants };
