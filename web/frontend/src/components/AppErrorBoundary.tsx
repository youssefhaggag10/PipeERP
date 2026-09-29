import { Component, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle, House, RefreshCw } from "lucide-react";

type Props = { children: ReactNode };
type State = { failed: boolean };

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("PipeERP page render failed", error, info.componentStack);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="fatal-error" role="alert">
        <div className="fatal-error__card">
          <span className="fatal-error__icon"><AlertTriangle size={30} /></span>
          <h1>تعذر عرض هذه الصفحة</h1>
          <p>بياناتك لم تُحذف. أعد تحميل الصفحة، وإذا تكرر العطل ارجع للرئيسية وجرب مرة أخرى.</p>
          <div className="fatal-error__actions">
            <button type="button" className="primary-button" onClick={() => window.location.reload()}>
              <RefreshCw size={17} /> إعادة التحميل
            </button>
            <a className="secondary-button" href="/"><House size={17} /> الصفحة الرئيسية</a>
          </div>
        </div>
      </main>
    );
  }
}
