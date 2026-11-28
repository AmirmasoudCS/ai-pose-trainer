"""A small tkinter window to select, create and delete profiles (tkinter ships with Python)."""


def manage_profiles(store, current_id):
    """Show the profile window. Returns the id of the selected profile (or None)."""
    try:
        import tkinter as tk
        from tkinter import messagebox, simpledialog
    except ImportError:
        print("tkinter is not available, so profiles cannot be managed from the app.")
        return current_id

    root = tk.Tk()
    root.title("Profiles")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    result = {"id": current_id}
    ids = []

    tk.Label(root, text="Select a profile, or create a new one:", anchor="w").pack(
        fill="x", padx=12, pady=(12, 4))
    listbox = tk.Listbox(root, width=36, height=10, exportselection=False, font=("Segoe UI", 11))
    listbox.pack(padx=12, pady=4)

    def refresh(select_id=None):
        listbox.delete(0, "end")
        ids.clear()
        for p in store.profiles():
            ids.append(p["id"])
            listbox.insert("end", f"{p['name']}   ({len(p['records'])} workouts)")
        target = select_id or result["id"]
        if target in ids:
            listbox.selection_set(ids.index(target))

    def selected_id():
        selection = listbox.curselection()
        return ids[selection[0]] if selection else None

    def do_select():
        pid = selected_id()
        if pid is None:
            messagebox.showinfo("Profiles", "Select a profile in the list first.", parent=root)
            return
        result["id"] = pid
        root.destroy()

    def do_new():
        name = simpledialog.askstring("New profile", "Name (max 20 characters):", parent=root)
        if not name:
            return
        try:
            pid = store.add_profile(name)
        except ValueError as exc:
            messagebox.showwarning("Profiles", str(exc), parent=root)
            return
        except OSError as exc:
            messagebox.showerror("Profiles", f"Could not save the profile:\n{exc}", parent=root)
            return
        result["id"] = pid  # a new profile becomes the active one
        refresh(pid)

    def do_delete():
        pid = selected_id()
        if pid is None:
            return
        profile = store.get(pid)
        if not messagebox.askyesno(
            "Delete profile",
            f"Delete '{profile['name']}' and all {len(profile['records'])} saved workouts?\n"
            "This cannot be undone.",
            parent=root,
        ):
            return
        try:
            store.delete_profile(pid)
        except OSError as exc:
            messagebox.showerror("Profiles", f"Could not delete the profile:\n{exc}", parent=root)
            return
        if result["id"] == pid:
            result["id"] = None
        refresh()

    row = tk.Frame(root)
    row.pack(fill="x", padx=12, pady=(6, 12))
    tk.Button(row, text="Select", width=10, command=do_select).pack(side="left", padx=(0, 6))
    tk.Button(row, text="New...", width=10, command=do_new).pack(side="left", padx=6)
    tk.Button(row, text="Delete", width=10, command=do_delete).pack(side="left", padx=6)
    tk.Button(row, text="Close", width=8, command=root.destroy).pack(side="right")

    listbox.bind("<Double-Button-1>", lambda _e: do_select())
    refresh()
    root.focus_force()
    root.mainloop()
    return result["id"]