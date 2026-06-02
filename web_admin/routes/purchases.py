{% extends "base.html" %}

{% block page_title %}Покупки{% endblock %}

{% block content %}
<div class="d-flex justify-content-between align-items-center mb-3">
    <form method="get" class="d-flex">
        <input type="text" name="client_search" class="form-control me-2" placeholder="Поиск по клиенту" value="{{ client_search }}">
        <button class="btn btn-primary" type="submit">Найти</button>
    </form>
</div>

<div class="card">
    <div class="table-responsive">
        <table class="table table-hover">
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Клиент</th>
                    <th>Дата</th>
                    <th>Сумма</th>
                    <th>Тип</th>
                    <th>Действия</th>
                </tr>
            </thead>
            <tbody>
                {% for p in purchases %}
                <tr>
                    <td>{{ p.id }}</td>
                    <td>{{ p.client_name or '—' }}</td>
                    <td>{{ p.created_at|format_date }}</td>
                    <td>{{ "{:,.0f}".format(p.total_amount or 0) }} ₽</td>
                    <td>{{ p.purchase_type }}</td>
                    <td>
                        <form action="/admin/purchases/delete/{{ p.id }}" method="post">
                            <button type="submit" class="btn btn-sm btn-outline-danger" onclick="return confirm('Удалить покупку?')">Удалить</button>
                        </form>
                    </td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="6" class="text-center text-muted">Покупок не найдено</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
{% endblock %}
