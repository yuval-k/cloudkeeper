extends Control

var is_visible := false

onready var anim_tween = $AnimTween
onready var orig_pos = rect_position

var selected_node : CloudNode = null

func _ready() -> void:
	hide()
	rect_position.y = orig_pos.y + 300
	_e.connect("nodeinfo_show", self, "show_info")
	_e.connect("nodeinfo_hide", self, "hide_info")


func hide_info() -> void:
	selected_node = null
	anim_tween.interpolate_property(self, "modulate:a", modulate.a, 0, 0.2, Tween.TRANS_QUART, Tween.EASE_OUT)
	anim_tween.interpolate_property(self, "rect_position:y", rect_position.y, orig_pos.y + 300, 0.3, Tween.TRANS_QUART, Tween.EASE_OUT)
	anim_tween.start()


func show_info(target_node) -> void:
	selected_node = target_node
	$Background/NodeNameLabel.text = target_node.reported.name
	$Background/NodeNameLabel/NodeKindLabel.text = target_node.reported.kind
	
	var text_infos := ""
	if "ctime" in target_node.reported:
		text_infos += "[b]ctime[/b]\n"
		text_infos += "   date: [color=white]" + str( target_node.reported.ctime.split("T")[0] ) + "[/color]\n"
		text_infos += "   time: [color=white]" + str( target_node.reported.ctime.split("T")[1] ) + "[/color]\n\n"
	if "tags" in target_node.reported:
		if !target_node.reported.tags.empty():
			text_infos += "[b]tags[/b]\n   "
			for tag in target_node.reported.tags:
				text_infos += "[[color=white]" + str(tag) + "[/color]] , "
		text_infos = text_infos.rstrip(" , ")
	
	$Background/NodeInfoLabel.bbcode_text = text_infos
	
	show()
	anim_tween.interpolate_property(self, "modulate:a", modulate.a, 1, 0.2, Tween.TRANS_QUART, Tween.EASE_OUT)
	anim_tween.interpolate_property(self, "rect_position:y", rect_position.y, orig_pos.y, 0.3, Tween.TRANS_QUART, Tween.EASE_OUT)
	anim_tween.start()


func _on_AnimTween_tween_all_completed() -> void:
	if is_visible:
		hide()
		is_visible = false
	elif is_visible and modulate.a == 1:
		is_visible = true


func _on_MarkForCleanupButton_pressed():
	_e.emit_signal("show_blastradius", selected_node.id)
