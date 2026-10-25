"use client";
import { useEffect, useState } from "react";
import { ArrowUpLeft, ArrowLeft, ClipboardList, RefreshCw, Info } from "lucide-react";
import { request } from "@/lib/api";
import { date, number } from "@/lib/format";
import { resources, systems } from "@/lib/resources";
import type { Dashboard as DashboardData, System, User } from "@/lib/types";
import { Empty, ErrorBox, Loading, Status } from "./Shared";

export function Dashboard({
  system,
  token,
  user,
  navigate,
}: {
  system: System;
  token: string;
  user: User;
  navigate: (key: string) => void;
}) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    request<DashboardData>(system, token, "/dashboard")
      .then((result) => {
        if (alive) setData(result);
      })
      .catch((reason) => {
        if (alive) setError(reason.message);
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [system, token, revision]);
  const available = resources[system].filter(
    (resource) => !resource.managerOnly || user.role !== "staff",
  );
  const primary = available[0];
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>نمای کلی {systems[system].noun}</h1>
          <p>{user.full_name}، خوش آمدید. وضعیت امروز و آخرین فعالیت‌ها را مرور کنید.</p>
        </div>
        <button
          className="button secondary"
          onClick={() => setRevision((value) => value + 1)}
          disabled={loading}
        >
          <RefreshCw size={17} />
          تازه‌سازی
        </button>
      </div>
      {error ? (
        <ErrorBox message={error} retry={() => setRevision((value) => value + 1)} />
      ) : loading ? (
        <Loading rows={4} />
      ) : (
        data && (
          <>
            <section className="metrics" aria-label="آمار سامانه">
              {data.metrics.map((metric, i) => (
                <div className="metric" key={i}>
                  <span>{metric.label}</span>
                  <div>
                    <strong>
                      {typeof metric.value === "number" ? number(metric.value) : metric.value}
                    </strong>
                    {metric.unit && <small>{metric.unit}</small>}
                  </div>
                </div>
              ))}
            </section>
            <div className="dashboard-columns">
              <section className="activity ledger">
                <div className="section-heading">
                  <div>
                    <h2>آخرین فعالیت‌ها</h2>
                    <p>تازه‌ترین اطلاعات ثبت‌شده در این سامانه</p>
                  </div>
                  <ClipboardList size={21} className="muted" />
                </div>
                {data.recent.length ? (
                  <div className="activity-list">
                    {data.recent.map((entry, i) => (
                      <div className="activity-row" key={i}>
                        <span className="activity-marker" />
                        <div className="activity-content">
                          <strong>{entry.title}</strong>
                          <p>{entry.subtitle}</p>
                        </div>
                        <div className="activity-meta">
                          {entry.status && <Status value={entry.status} />}
                          <time>{date(entry.date)}</time>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <Empty
                    title="فعالیت تازه‌ای ثبت نشده است"
                    detail="پس از ثبت اطلاعات، آخرین موارد را اینجا می‌بینید."
                  />
                )}
              </section>
              <aside className="dashboard-aside">
                <section className="work-shortcuts">
                  <h2>فضای کاری شما</h2>
                  <p>دسترسی سریع به بخش‌های پرکاربرد</p>
                  <div>
                    {available.slice(0, 4).map((resource) => (
                      <button key={resource.key} onClick={() => navigate(resource.key)}>
                        <span>{resource.title}</span>
                        <ArrowUpLeft size={18} />
                      </button>
                    ))}
                  </div>
                </section>
                {data.notices.length > 0 && (
                  <section className="notices">
                    <h2>نیازمند توجه</h2>
                    {data.notices.map((notice, i) => (
                      <div className="notice" key={i}>
                        <Info size={18} />
                        <div>
                          <strong>{notice.title}</strong>
                          <p>{notice.detail}</p>
                        </div>
                      </div>
                    ))}
                  </section>
                )}
              </aside>
            </div>
            <section className="dashboard-bottom">
              <div>
                <h2>
                  {system === "personnel"
                    ? "اطلاعات همکاران، یک‌جا و قابل پیگیری"
                    : system === "inventory"
                      ? "از ورود کالا تا بازگشت تجهیزات"
                      : "از نخستین پیشنهاد تا تسویه قرارداد"}
                </h2>
                <p>
                  {system === "personnel"
                    ? "پرونده هر کارمند، نقطه شروع قرارداد، مرخصی و محاسبه حقوق است."
                    : system === "inventory"
                      ? "هر گردش انبار و هر تحویل به کارمند، سابقه مستقل خود را دارد."
                      : "اطلاعات مشتری، پیشنهاد قیمت و اسناد مالی را در مسیر مشخص نگه دارید."}
                </p>
              </div>
              <button className="text-button" onClick={() => navigate(primary.key)}>
                مشاهده {primary.title}
                <ArrowLeft size={18} />
              </button>
            </section>
          </>
        )
      )}
    </>
  );
}
