import { LucideIcon } from "lucide-react";
import { InputHTMLAttributes } from "react";

type Props = InputHTMLAttributes<HTMLInputElement> & { icon: LucideIcon };

export default function IconInput({ icon: Icon, className = "", ...rest }: Props) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-border bg-panel-2 px-3 py-2.5">
      <Icon className="h-4 w-4 shrink-0 text-text-faint" />
      <input {...rest} className={`w-full bg-transparent text-sm text-text placeholder:text-text-faint focus:outline-none ${className}`} />
    </div>
  );
}
