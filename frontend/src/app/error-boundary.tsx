import { Component, type ErrorInfo, type ReactNode } from "react";

export class ScreenErrorBoundary extends Component<{children:ReactNode},{failed:boolean}> {
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  componentDidCatch(error:Error,info:ErrorInfo){console.error("Screen render failed",error,info);}
  render(){return this.state.failed?<section role="alert" className="rounded border border-red-300 bg-red-50 p-5"><h1 className="text-xl font-bold">This page could not be displayed.</h1><p>The application shell is still available. Reload after the server response is corrected.</p><button className="mt-3 rounded bg-slate-900 px-3 py-2 text-white" onClick={()=>location.reload()}>Reload page</button></section>:this.props.children;}
}
