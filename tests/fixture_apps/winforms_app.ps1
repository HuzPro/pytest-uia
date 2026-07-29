# Fixture app with a rich accessibility tree, driven by the UIA specs.
# It stands in for the kind of surface that exposes everything without being
# asked: a WinForms or WPF app, or an Electron window, where every control
# arrives already named and correctly roled.
#
# Launch it the way the tests do:
#   powershell.exe -NoProfile -Sta -WindowStyle Hidden -ExecutionPolicy Bypass -File winforms_app.ps1
# -Sta is not optional: WinForms refuses to run outside a single-threaded apartment.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

[System.Windows.Forms.Application]::EnableVisualStyles()

$form = New-Object System.Windows.Forms.Form
$form.Text = 'pytest-uia WinForms Fixture'
$form.ClientSize = New-Object System.Drawing.Size(420, 240)
$form.StartPosition = 'CenterScreen'
# Kept in front so the mouse and OCR fallbacks act on this window rather than on
# whatever the developer happened to leave focused.
$form.TopMost = $true

$status = New-Object System.Windows.Forms.Label
$status.Text = 'ready'
$status.AutoSize = $true
$status.Location = New-Object System.Drawing.Point(20, 20)

$title = New-Object System.Windows.Forms.TextBox
$title.AccessibleName = 'Title'
$title.Location = New-Object System.Drawing.Point(20, 55)
$title.Size = New-Object System.Drawing.Size(360, 26)

$newTask = New-Object System.Windows.Forms.Button
$newTask.Text = 'New Task'
$newTask.Location = New-Object System.Drawing.Point(20, 105)
$newTask.Size = New-Object System.Drawing.Size(120, 36)
$newTask.Add_Click({ $status.Text = 'task created' })

# A list whose provider really exposes its rows, which Tk's never does: the
# surface the list_item role exists for.
$tasks = New-Object System.Windows.Forms.ListBox
$tasks.AccessibleName = 'Tasks'
$tasks.Location = New-Object System.Drawing.Point(160, 105)
$tasks.Size = New-Object System.Drawing.Size(220, 70)
[void]$tasks.Items.Add('water the plants')
[void]$tasks.Items.Add('file the report')
# Enough rows that the last ones have no pixels: what scroll_into_view is for.
foreach ($n in 1..12) { [void]$tasks.Items.Add("backlog item $n") }

$form.Controls.AddRange(@($status, $title, $newTask, $tasks))

[System.Windows.Forms.Application]::Run($form)
