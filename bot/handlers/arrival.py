@router.callback_query(ArrivalConfirmState.waiting_for_confirm, F.data.startswith("arrival_confirm:"))
async def process_arrival_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items = data.get("temp_items", [])
    action = callback.data.split(":")[1]

    if action != "yes" or not items:
        await callback.message.edit_text("❌ Загрузка отменена.")
        await state.clear()
        await callback.answer()
        return

    added = 0
    failed_items = []

    for item_data in items:
        try:
            category_name = item_data.get('category', 'Без категории')

            # Пытаемся создать категорию (если нужно)
            await get_or_create_category(category_name)

            # Добавляем товар
            success = await ItemRepository.add_item(
                text=item_data['text'],
                serial=item_data.get('serial'),
                category_name=category_name
            )

            if success:
                added += 1
            else:
                failed_items.append(item_data['text'])

        except Exception as e:
            logger.warning(f"Не удалось добавить товар: {item_data['text']} | Ошибка: {e}")
            failed_items.append(item_data['text'])

    # Формируем ответ
    if added > 0 and not failed_items:
        text = f"✅ Успешно добавлено {added} товаров в ассортимент!"
    elif added > 0 and failed_items:
        text = f"✅ Добавлено {added} товаров.\n\n"
        text += "❌ Не удалось добавить:\n"
        for item in failed_items[:8]:  # показываем максимум 8
            text += f"• {item}\n"
        if len(failed_items) > 8:
            text += f"... и ещё {len(failed_items) - 8} товаров"
    else:
        text = "❌ Не удалось добавить ни одного товара."

    await callback.message.edit_text(text)
    await state.clear()
    await callback.answer()
