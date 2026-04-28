'use client';

import { useEffect, useState } from 'react';
import { useOrganization } from '@/contexts/OrganizationContext';

interface OrgCourse {
  id: string;
  course_id: string;
  title: string;
  visible: boolean;
  order_index: number;
}

export default function AdminCoursesPage() {
  const { org } = useOrganization();
  const [courses, setCourses] = useState<OrgCourse[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!org?.id) return;
    fetchCourses();
  }, [org?.id]);

  async function fetchCourses() {
    if (!org?.id) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/admin/organizations/${org.id}/content`);
      if (res.ok) {
        const data = await res.json();
        setCourses(data.courses || []);
      }
    } finally {
      setLoading(false);
    }
  }

  async function toggleVisibility(courseId: string, visible: boolean) {
    if (!org?.id) return;
    const updated = courses.map(c =>
      c.course_id === courseId ? { ...c, visible } : c
    );
    setCourses(updated);
    await saveCourses(updated);
  }

  async function moveUp(index: number) {
    if (index === 0) return;
    const updated = [...courses];
    [updated[index - 1], updated[index]] = [updated[index], updated[index - 1]];
    updated.forEach((c, i) => { c.order_index = i; });
    setCourses(updated);
    await saveCourses(updated);
  }

  async function moveDown(index: number) {
    if (index >= courses.length - 1) return;
    const updated = [...courses];
    [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
    updated.forEach((c, i) => { c.order_index = i; });
    setCourses(updated);
    await saveCourses(updated);
  }

  async function saveCourses(updated: OrgCourse[]) {
    if (!org?.id) return;
    setSaving(true);
    try {
      await fetch(`/api/admin/organizations/${org.id}/content`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          courses: updated.map(c => ({
            course_id: c.course_id,
            visible: c.visible,
            order_index: c.order_index,
          })),
        }),
      });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Courses</h1>
        {saving && (
          <span className="text-xs text-gray-500">Saving...</span>
        )}
      </div>

      <div className="rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        {loading ? (
          <div className="px-4 py-8 text-center text-gray-500">Loading courses...</div>
        ) : courses.length === 0 ? (
          <div className="px-4 py-8 text-center text-gray-500">
            No courses assigned. Courses will appear here once configured.
          </div>
        ) : (
          <ul className="divide-y divide-gray-200 dark:divide-gray-700">
            {courses.map((course, idx) => (
              <li key={course.course_id} className="flex items-center gap-4 px-4 py-3">
                {/* Reorder controls */}
                <div className="flex flex-col gap-0.5">
                  <button
                    onClick={() => moveUp(idx)}
                    disabled={idx === 0}
                    className="text-gray-400 hover:text-gray-600 disabled:opacity-30 text-xs"
                    aria-label="Move up"
                  >
                    ▲
                  </button>
                  <button
                    onClick={() => moveDown(idx)}
                    disabled={idx === courses.length - 1}
                    className="text-gray-400 hover:text-gray-600 disabled:opacity-30 text-xs"
                    aria-label="Move down"
                  >
                    ▼
                  </button>
                </div>

                {/* Course info */}
                <div className="flex-1 min-w-0">
                  <span className={`text-sm font-medium ${course.visible ? 'text-gray-900 dark:text-gray-100' : 'text-gray-400 line-through'}`}>
                    {course.title}
                  </span>
                </div>

                {/* Visibility toggle */}
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={course.visible}
                    onChange={e => toggleVisibility(course.course_id, e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-9 h-5 bg-gray-200 peer-focus:outline-none rounded-full peer dark:bg-gray-600 peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-blue-600" />
                  <span className="ml-2 text-xs text-gray-500">
                    {course.visible ? 'Visible' : 'Hidden'}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
