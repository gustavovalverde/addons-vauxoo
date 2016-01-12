# coding: utf-8

from openerp import models, fields
import openerp.addons.decimal_precision as dp
SEGMENTATION = ['material', 'landed', 'production', 'subcontracting']


class StockCardProduct(models.TransientModel):
    _inherit = ['stock.card.product']

    def _get_quant_values(self, move_id, col='', inner='', where=''):

        col = ['%s_cost' % sgmnt for sgmnt in SEGMENTATION]
        col = ['COALESCE(%s, 0.0) AS %s' % (cl, cl) for cl in col]
        col = ', ' + ', '.join(col)
        return super(StockCardProduct, self)._get_quant_values(
            move_id=move_id, col=col, inner=inner, where=where)

    def _get_stock_card_move_line_dict(self, row, vals):
        res = super(StockCardProduct, self)._get_stock_card_move_line_dict(
            row, vals)
        res = dict(
            res,
            material=vals['material'],
            landed=vals['landed'],
            production=vals['production'],
            subcontracting=vals['subcontracting'],
        )
        return res

    def _get_default_params(self):
        res = super(StockCardProduct, self)._get_default_params()
        res.update({}.fromkeys(SEGMENTATION, 0.0))
        res.update({}.fromkeys(
            ['%s_total' % sgmnt for sgmnt in SEGMENTATION], 0.0))
        res.update({}.fromkeys(
            ['%s_valuation' % sgmnt for sgmnt in SEGMENTATION], 0.0))
        res.update({}.fromkeys(
            ['%s_accum_var' % sgmnt for sgmnt in SEGMENTATION], 0.0))
        return res

    def _get_price_on_consumed(self, row, vals, qntval):
        move_id = row['move_id']
        product_qty = vals['product_qty']
        delta_qty = vals['direction'] * row['product_qty']
        final_qty = product_qty + delta_qty
        vals['product_qty'] += (vals['direction'] * row['product_qty'])

        if not vals['move_dict'].get(move_id):
            vals['move_dict'][move_id] = {}

        vals['move_dict'][move_id]['average'] = vals['average']
        for sgmnt in SEGMENTATION:
            vals['move_dict'][move_id][sgmnt] = vals[sgmnt]

        antiquant = any([qnt['antiquant'] for qnt in qntval])
        if final_qty < 0 and antiquant:
            vals['move_dict'][move_id]['average'] = vals['average']
            vals['move_valuation'] = sum(
                [vals['average'] * qnt['qty'] for qnt in qntval
                 if qnt['qty'] > 0])
            for sgmnt in SEGMENTATION:
                vals['move_dict'][move_id][sgmnt] = vals[sgmnt]
                vals['%s_valuation' % sgmnt] = sum(
                    [vals[sgmnt] * qnt['qty'] for qnt in qntval
                     if qnt['qty'] > 0])
            return True

        vals['move_valuation'] = 0.0
        for sgmnt in SEGMENTATION:
            vals['%s_valuation' % sgmnt] = 0.0

        for qnt in qntval:
            if qnt['qty'] < 0:
                continue
            product_qty += vals['direction'] * qnt['qty']
            if product_qty >= 0:
                if not vals['rewind']:
                    vals['move_valuation'] += vals['average'] * qnt['qty']
                    for sgmnt in SEGMENTATION:
                        vals['%s_valuation' % sgmnt] += \
                            vals[sgmnt] * qnt['qty']
                else:
                    vals['move_valuation'] += \
                        vals['prior_average'] * qnt['qty']
                    for sgmnt in SEGMENTATION:
                        vals['%s_valuation' % sgmnt] += \
                            vals['prior_avg_%s' % sgmnt] * qnt['qty']
            else:
                if not vals['rewind']:
                    vals['move_valuation'] += vals['average'] * qnt['qty']
                    for sgmnt in SEGMENTATION:
                        vals['%s_valuation' % sgmnt] += \
                            vals[sgmnt] * qnt['qty']
                else:
                    vals['move_valuation'] += \
                        vals['future_average'] * qnt['qty']
                    for sgmnt in SEGMENTATION:
                        vals['%s_valuation' % sgmnt] += \
                            vals['future_%s' % sgmnt] * qnt['qty']

        return True

    def _get_price_on_supplier_return(self, row, vals, qntval):
        vals['product_qty'] += (vals['direction'] * row['product_qty'])
        sm_obj = self.env['stock.move']
        move_id = row['move_id']
        move_brw = sm_obj.browse(move_id)
        vals['move_valuation'] = sum([move_brw.price_unit * qnt['qty']
                                      for qnt in qntval])
        for sgmnt in SEGMENTATION:
            vals['%s_valuation' % sgmnt] = sum(
                [qnt['%s_cost' % sgmnt] * qnt['qty'] for qnt in qntval])

        return True

    def _get_price_on_supplied(self, row, vals, qntval):
        vals['product_qty'] += (vals['direction'] * row['product_qty'])
        vals['move_valuation'] = sum(
            [qnt['cost'] * qnt['qty'] for qnt in qntval])

        for sgmnt in SEGMENTATION:
            vals['%s_valuation' % sgmnt] = sum(
                [qnt['%s_cost' % sgmnt] * qnt['qty'] for qnt in qntval])

        return True

    def _get_price_on_customer_return(self, row, vals, qntval):
        vals['product_qty'] += (vals['direction'] * row['product_qty'])
        sm_obj = self.env['stock.move']
        move_id = row['move_id']
        move_brw = sm_obj.browse(move_id)
        origin_id = move_brw.origin_returned_move_id.id
        old_average = (
            vals['move_dict'].get(origin_id, 0.0) and
            vals['move_dict'][move_id]['average'] or vals['average'])
        vals['move_valuation'] = sum(
            [old_average * qnt['qty'] for qnt in qntval])

        for sgmnt in SEGMENTATION:
            old_average = (
                vals['move_dict'].get(origin_id, 0.0) and
                vals['move_dict'][move_id][sgmnt] or
                vals[sgmnt])

            vals['%s_valuation' % sgmnt] = sum(
                [old_average * qnt['qty'] for qnt in qntval])

        return True

    def _get_move_average(self, row, vals):
        qty = row['product_qty']
        vals['cost_unit'] = vals['move_valuation'] / qty if qty else 0.0

        vals['inventory_valuation'] += (
            vals['direction'] * vals['move_valuation'])
        for sgmnt in SEGMENTATION:
            vals['%s_total' % sgmnt] += (
                vals['direction'] * vals['%s_valuation' % sgmnt])

        if vals['previous_qty'] < 0 and vals['direction'] > 0:
            vals['accumulated_variation'] += vals['move_valuation']
            vals['accumulated_qty'] += row['product_qty']
            for sgmnt in SEGMENTATION:
                vals['%s_accum_var' % sgmnt] += vals['%s_valuation' % sgmnt]

            vals['average'] = (
                vals['accumulated_qty'] and
                vals['accumulated_variation'] / vals['accumulated_qty'] or
                vals['average'])
            for sgmnt in SEGMENTATION:
                vals[sgmnt] = (
                    vals['accumulated_qty'] and
                    vals['%s_accum_var' % sgmnt] / vals['accumulated_qty'] or
                    vals[sgmnt])

            if vals['product_qty'] >= 0:
                vals['accumulated_variation'] = 0.0
                vals['accumulated_qty'] = 0.0
                for sgmnt in SEGMENTATION:
                    vals['%s_accum_var' % sgmnt] = 0.0
        else:
            vals['average'] = (
                vals['product_qty'] and
                vals['inventory_valuation'] / vals['product_qty'] or
                vals['average'])
            for sgmnt in SEGMENTATION:
                vals[sgmnt] = (
                    vals['product_qty'] and
                    vals['%s_total' % sgmnt] / vals['product_qty'] or
                    vals[sgmnt])
        pass

        return True

    def _pre_get_average_by_move(self, row, vals):
        vals['previous_qty'] = vals['product_qty']
        vals['previous_valuation'] = vals['inventory_valuation']
        vals['previous_average'] = vals['average']
        for sgmnt in SEGMENTATION:
            vals['previous_val_%s' % sgmnt] = vals['%s_total' % sgmnt]
            vals['previous_avg%s' % sgmnt] = vals[sgmnt]
        return True

    def _post_get_average_by_move(self, row, vals):
        if not vals['rewind']:
            if vals['previous_qty'] > 0 and vals['product_qty'] < 0:
                vals['prior_qty'] = vals['previous_qty']
                vals['prior_valuation'] = vals['previous_valuation']
                vals['prior_average'] = vals['previous_average']

                for sgmnt in SEGMENTATION:
                    vals['prior_val_%s' % sgmnt] = \
                        vals['previous_val_%s' % sgmnt]
                    vals['prior_avg_%s' % sgmnt] = \
                        vals['previous_avg%s' % sgmnt]

            if vals['product_qty'] < 0 and vals['direction'] < 0:
                vals['accumulated_move'].append(row)
            elif vals['previous_qty'] < 0 and vals['direction'] > 0:
                vals['accumulated_move'].append(row)
                vals['rewind'] = True
                vals['old_queue'] = vals['queue'][:]
                vals['queue'] = vals['accumulated_move'][:]

                vals['product_qty'] = vals['prior_qty']
                vals['inventory_valuation'] = vals['prior_valuation']
                vals['future_average'] = vals['average']

                for sgmnt in SEGMENTATION:
                    vals['%s_total' % sgmnt] = \
                        vals['prior_val_%s' % sgmnt]
                    vals['future_%s' % sgmnt] = vals[sgmnt]

                vals['accumulated_variation'] = 0.0
                vals['accumulated_qty'] = 0.0
                for sgmnt in SEGMENTATION:
                    vals['%s_accum_var' % sgmnt] = 0.0

        else:
            if not vals['queue']:
                vals['rewind'] = False
                vals['queue'] = vals['old_queue'][:]

            if vals['product_qty'] > 0:
                vals['accumulated_move'] = []
        return True


class StockCardMove(models.TransientModel):
    _inherit = 'stock.card.move'
    material = fields.Float(
        string='Material Cost',
        digits=dp.get_precision('Account'),
        readonly=True)
    landed = fields.Float(
        string='Landed Cost',
        digits=dp.get_precision('Account'),
        readonly=True)
    production = fields.Float(
        string='Production Cost',
        digits=dp.get_precision('Account'),
        readonly=True)
    subcontracting = fields.Float(
        string='Subcontracting Cost',
        digits=dp.get_precision('Account'),
        readonly=True)